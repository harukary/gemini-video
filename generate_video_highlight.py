import base64
import json
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
from pydantic import BaseModel, Field
from litellm import completion
import argparse
import os
from tqdm import tqdm

def merge_videos_with_timestamp(input_dir, output_path, refresh=False):
    FPS = None
    # 入力ディレクトリから全ての動画ファイルを取得
    input_dir = Path(input_dir).resolve()
    video_files = list(input_dir.glob('**/*.MP4'))
    if not video_files:
        print('動画ファイルが見つかりませんでした。')
        return None, None, None
    video_files.sort()

    # 合計ファイルサイズを計算
    total_size = sum(os.path.getsize(f) for f in video_files)

    # 動画クリップのリストを作成
    video_clips = []
    original_clips = []  # 圧縮前のクリップを保持
    for video_path in video_files:
        print(f'読み込み中: {video_path.name}')
        try:
            clip = VideoFileClip(str(video_path))
            original_clips.append(clip)  # 元のクリップを保存
            # clip = clip.resize(height=240)
            video_clips.append(clip)
        except Exception as e:
            print(f'エラー: {video_path.name} の読み込みに失敗しました - {str(e)}')
            continue

    if not video_clips:
        print('処理可能な動画がありませんでした。')
        return None, None, None

    # 動画を連結
    try:
        original_final_clip = concatenate_videoclips(original_clips)  # 圧縮前の連結クリップ
        if not refresh:
            final_clip_with_text = VideoFileClip(output_path)
        else:
            final_clip = concatenate_videoclips(video_clips)
            if FPS is None:
                FPS = final_clip.fps

            target_size = 10 * 1024 * 1024
            print(f"{total_size} -> {target_size}")
            target_bitrate = int((target_size * 8) / final_clip.duration)
            target_bitrate_str = f"{target_bitrate//1000}k"
            audio_bitrate = "32k"  # 音声ビットレートを低く設定

            # 秒数テキストを追加
            def make_text_clip(t):
                return TextClip(
                    f"{t:.0f}秒", fontsize=24, color='white', bg_color='rgba(0,0,0,0.7)'
                ).set_position(("right", "top")).set_duration(1/FPS).set_start(t)

            print(f"秒数テキストを追加")
            text_clips = [make_text_clip(t/FPS) for t in range(0, int(final_clip.duration * FPS), 1)]
            print(len(text_clips))
            # デバッグ情報の出力
            print(f"動画の長さ: {final_clip.duration}秒")
            print(f"テキストクリップの数: {len(text_clips)}")
            print(f"最後のテキストクリップの開始時間: {text_clips[-1].start if text_clips else 'なし'}")

            # テキストクリップの時間が動画の長さを超えていないか確認
            if text_clips and text_clips[-1].start + text_clips[-1].duration > final_clip.duration:
                print("警告: テキストクリップが動画の長さを超えています")
                # 超過分を削除
                text_clips = [clip for clip in text_clips if clip.start + clip.duration <= final_clip.duration]

            final_clip_with_text = CompositeVideoClip([final_clip] + text_clips)

            # Gemini用の圧縮動画を書き出し
            print('動画を書き出し中...')
            final_clip_with_text.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                audio_bitrate=audio_bitrate,  # 音声ビットレートを指定
                threads=4,
                preset='ultrafast',
                fps=FPS,
                bitrate=target_bitrate_str
            )
            print('動画の処理が完了しました。')
        return output_path, final_clip_with_text, original_final_clip
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return None, None, None

def create_highlight_video(video_clip, output_path, highlights):
    clips = []
    for highlight in highlights:
        start = highlight.start_second
        end = highlight.end_second
        if start > video_clip.duration:
            continue
        if end > video_clip.duration:
            end = video_clip.duration
        clip = video_clip.subclip(start, end)
        clips.append(clip)

    final_video = concatenate_videoclips(clips)
    text_clips = []
    current_time = 0
    for highlight in highlights:
        if highlight.start_second > video_clip.duration:
            continue
        end = min(highlight.end_second, video_clip.duration)
        clip_duration = end - highlight.start_second

        for narration in highlight.narration:
            # ナレーションの相対時間を計算
            relative_start = current_time + (narration.start_second - highlight.start_second)
            relative_end = relative_start + (narration.end_second - narration.start_second)
            text_clip = TextClip(
                narration.narration,
                fontsize=24,
                font='/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc',
                color='white',
                bg_color='rgba(0,0,0,0.5)',
                size=(final_video.w, None),
                method='caption'
            ).set_position(
                ('center', 'bottom')
            ).set_duration(
                relative_end - relative_start
            ).set_start(relative_start)
            text_clips.append(text_clip)
        current_time += clip_duration

    final_video = CompositeVideoClip([final_video] + text_clips)
    # 出力パスを生成（元のファイル名から_highlightを付加）
    output_path = str(Path(output_path).with_suffix(".mp4").with_stem(Path(output_path).stem + "_highlight"))
    minutes = int(final_video.duration // 60)
    seconds = int(final_video.duration % 60)
    print(f"ハイライト動画の長さ: {minutes:02d}:{seconds:02d}")
    final_video.write_videofile(output_path)
    # メモリリーク防止のためにクリップを閉じる
    for clip in clips:
        clip.close()
    return output_path

class Narration(BaseModel):
    narration: str = Field(..., description="ナレーション")
    start_second: float = Field(..., description="開始秒数")
    end_second: float = Field(..., description="終了秒数")

class VideoHighlight(BaseModel):
    start_second: float = Field(..., description="開始秒数")
    end_second: float = Field(..., description="終了秒数")
    narration: list[Narration] = Field(..., description="複数のナレーション")

class VideoHighlights(BaseModel):
    highlights: list[VideoHighlight] = Field(..., description="5~10秒のハイライトのリスト")

def main(input_directory, output_file, target_minutes=None, highlight_ratio=0.3, refresh=False):
    output_path = Path(output_file)
    merged_video_path = output_path
    json_path = output_path.with_suffix('.json')

    merged_path, preview_clip, original_clip = merge_videos_with_timestamp(input_directory, str(merged_video_path), refresh)
    if merged_path is None:
        return

    try:
        # 動画の長さを取得
        duration_minutes = int(preview_clip.duration) // 60
        if target_minutes:
            target_duration = min(target_minutes, duration_minutes)
        else:
            target_duration = int(duration_minutes * highlight_ratio)

        # プロンプトの読み込みと動的な値の設定
        duration_seconds = int(duration_minutes * 60)
        target_duration_seconds = int(target_duration * 60)
        print(f"{duration_seconds} -> {target_duration_seconds}")
        with open("prompts/prompt.md", "r") as f:
            prompt = f.read()
            prompt = prompt.format(
                duration=duration_seconds,
                target_duration=target_duration_seconds
            )

        # Geminiで動画解析（圧縮・秒数入れ後の動画を使用）
        print(f"Geminiで動画解析")
        video_bytes = Path(output_path).read_bytes()
        encoded_data = base64.b64encode(video_bytes).decode("utf-8")
        response = completion(
            model="gemini/gemini-2.0-flash-exp",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": "data:video/mp4;base64,{}".format(encoded_data),
                        },
                    ],
                }
            ],
            response_format=VideoHighlights,
        )
        # ハイライト動画の作成（圧縮前の元動画を使用）
        highlights = VideoHighlights.model_validate(json.loads(response.choices[0].message.content))
        # ハイライトをJSONファイルとして保存
        output_json_path = Path(output_file).with_suffix('.json')
        with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(highlights.model_dump(), f, ensure_ascii=False, indent=2)
        print(f"ハイライト情報をJSONに保存しました: {output_json_path}")
        print(highlights.highlights)
        highlight_video = create_highlight_video(original_clip, output_file, highlights.highlights)
        print(f"ハイライト動画を保存しました: {highlight_video}")
    finally:
        # 最後にクリップをクローズ
        if preview_clip:
            preview_clip.close()
        if original_clip:
            original_clip.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='動画のハイライト作成')
    parser.add_argument(
        '--input-dir', '-i', default='videos/tokyo',
        help='入力動画のディレクトリパス'
    )
    parser.add_argument(
        '--output-file', '-o', default='videos/tokyo.mp4',
        help='出力動画のファイルパス'
    )
    parser.add_argument(
        '--target-minutes', '-t', type=float,
        help='ハイライトの目標長さ（分）'
    )
    parser.add_argument(
        '--highlight-ratio', '-r', type=float, default=0.3,
        help='元動画に対するハイライトの長さの比率（デフォルト: 0.3）'
    )
    parser.add_argument(
        '--refresh', '-f', action='store_true',
        help='ハイライトを再生成するかどうか'
    )

    args = parser.parse_args()
    main(
        input_directory=args.input_dir,
        output_file=args.output_file,
        target_minutes=args.target_minutes,
        highlight_ratio=args.highlight_ratio,
        refresh=args.refresh
    )
