import os, base64, json
from pathlib import Path
from pydantic import BaseModel, Field
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
from litellm import completion

FPS = 5
TARGET_VIDEO_SIZE_MB = 10

def merge_videos_with_timestamp(input_dir, output_path):
    input_dir = Path(input_dir).resolve()
    video_files = list(input_dir.glob('**/*.MP4'))
    if not video_files:
        print('動画ファイルが見つかりませんでした。')
        return None, None, None
    video_files.sort()

    video_clips = []
    original_clips = []
    final_clip = None
    final_clip_with_text = None
    original_final_clip = None
    text_clips = []
    
    try:
        total_duration = 0
        for video_path in video_files:
            print(f'読み込み中: {video_path.name}')
            try:
                # FFMPEGのオプションを追加して読み込みを安定化
                clip = VideoFileClip(
                    str(video_path),
                    audio=False,  # 音声は必要ない場合は無効化
                    fps_source='fps',  # fpsの取得方法を指定
                    verbose=False,  # 詳細なログを無効化
                    target_resolution=(240, None)  # 直接リサイズ指定
                )
                if clip.reader is None or not hasattr(clip, 'fps') or clip.fps is None:
                    print(f'警告: {video_path.name} の読み込みに失敗しました')
                    continue
                
                print(f'  Duration: {clip.duration:.2f}秒')
                print(f'  Size: {clip.size}')
                print(f'  FPS: {clip.fps}')
                
                total_duration += clip.duration
                video_clips.append(clip)
                
                # オリジナルクリップは最初のファイルのみ保持
                if len(original_clips) == 0:
                    original_clips.append(VideoFileClip(
                        str(video_path),
                        audio=False,
                        fps_source='fps',
                        verbose=False
                    ))
            except Exception as e:
                print(f'エラー: {video_path.name} の読み込みに失敗しました - {str(e)}')
                continue

        if not video_clips:
            print('処理可能な動画がありませんでした。')
            return None, None, None

        print('動画を連結中...')
        print(f'合計時間: {total_duration:.2f}秒')
        
        final_clip = concatenate_videoclips(video_clips, method="compose")
        target_size_bytes = TARGET_VIDEO_SIZE_MB * 1024 * 1024
        target_bitrate = int((target_size_bytes * 8) / final_clip.duration)
        target_bitrate_str = f"{target_bitrate//1000}k"

        print(f"秒数テキストを追加")
        def make_text_clip(t):
            actual_seconds = t / FPS
            return TextClip(
                f"{actual_seconds:.0f}秒", 
                fontsize=24, 
                color='white', 
                bg_color='rgba(0,0,0,0.7)',
                method='caption'
            ).set_position(("right", "top")).set_duration(1/FPS).set_start(actual_seconds)

        total_frames = int(final_clip.duration * FPS)
        # メモリ使用量を抑えるためにバッチ処理
        batch_size = 50  # バッチサイズを小さくする
        for i in range(0, total_frames, batch_size):
            batch_end = min(i + batch_size, total_frames)
            batch_clips = [make_text_clip(t) for t in range(i, batch_end)]
            text_clips.extend(batch_clips)
            if i % 500 == 0:  # 進捗表示
                print(f'  テキスト処理中: {i}/{total_frames} フレーム')

        final_clip_with_text = CompositeVideoClip([final_clip] + text_clips)

        print('動画を書き出し中...')
        final_clip_with_text.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            audio_bitrate='32k',
            threads=4,
            preset='ultrafast',
            fps=FPS,
            bitrate=target_bitrate_str,
            logger=None,
            verbose=False,
            ffmpeg_params=['-loglevel', 'error']  # FFMPEGのログレベルを制御
        )
        print('動画の処理が完了しました。')
        
        # クリーンアップ
        _cleanup_clips(video_clips + [final_clip, final_clip_with_text] + text_clips)
        
        return output_path, final_clip_with_text, original_clips[0]
        
    except Exception as e:
        import traceback
        print(f"エラーが発生しました: {e}")
        print(traceback.format_exc())
        return None, None, None
    finally:
        _cleanup_clips(video_clips + original_clips + [final_clip, final_clip_with_text] + text_clips)

def _cleanup_clips(clips):
    """クリップのクリーンアップを行うヘルパー関数"""
    for clip in clips:
        if clip is not None:
            try:
                if hasattr(clip, 'reader') and clip.reader is not None:
                    clip.reader.close()
                if hasattr(clip, 'audio') and clip.audio is not None:
                    clip.audio.reader.close_proc()
                clip.close()
            except Exception as e:
                print(f"クリップのクローズ中にエラーが発生: {e}")

def create_highlight_video(video_clip, output_path, highlights):
    if video_clip is None or not hasattr(video_clip, 'reader') or video_clip.reader is None:
        print("入力ビデオが無効です。")
        return None
        
    clips = []
    text_clips = []
    final_video = None
    final_composite = None
    
    try:
        print("\n=== 入力ビデオの情報 ===")
        print(f"duration: {video_clip.duration}")
        print(f"size: {video_clip.size}")
        print(f"fps: {video_clip.fps}")
        
        for highlight in highlights:
            start = highlight.start_second
            end = highlight.end_second
            if start > video_clip.duration:
                continue
            if end > video_clip.duration:
                end = video_clip.duration
            try:
                clip = video_clip.subclip(start, end)
                if clip.reader is not None:
                    clips.append(clip)
            except Exception as e:
                print(f"クリップの切り出し中にエラー: {e}")
                continue

        if not clips:
            print("有効なハイライトクリップがありません。")
            return None

        final_video = concatenate_videoclips(clips, method="compose")
        current_time = 0
        for highlight in highlights:
            if highlight.start_second > video_clip.duration:
                continue
            end = min(highlight.end_second, video_clip.duration)
            clip_duration = end - highlight.start_second

            for narration in highlight.narration:
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

        final_composite = CompositeVideoClip([final_video] + text_clips)
        output_path = str(Path(output_path).with_suffix(".mp4").with_stem(Path(output_path).stem + "_highlight"))
        minutes = int(final_composite.duration // 60)
        seconds = int(final_composite.duration % 60)
        print(f"ハイライト動画の長さ: {minutes:02d}:{seconds:02d}")
        
        final_composite.write_videofile(
            output_path,
            threads=4,
            codec='libx264',
            audio_codec='aac',
            fps=30
        )
        return output_path
        
    except Exception as e:
        import traceback
        print(f"ハイライト動画の生成中にエラーが発生しました: {e}")
        print("詳細なエラー情報:")
        print(traceback.format_exc())
        return None
        
    finally:
        for clip in clips:
            try:
                clip.close()
            except:
                pass
        for text_clip in text_clips:
            try:
                text_clip.close()
            except:
                pass
        if final_video:
            try:
                final_video.close()
            except:
                pass
        if final_composite:
            try:
                final_composite.close()
            except:
                pass

class Narration(BaseModel):
    narration: str = Field(..., description="ナレーション")
    start_second: float = Field(..., description="開始秒数")
    end_second: float = Field(..., description="終了秒数")

class VideoHighlight(BaseModel):
    start_second: float = Field(..., description="開始秒数")
    end_second: float = Field(..., description="終了秒数")
    narration: list[Narration] = Field(..., description="ナレーション")

class VideoHighlights(BaseModel):
    highlights: list[VideoHighlight] = Field(..., description="ハイライト")


def main(input_directory, output_file, target_minutes=None, highlight_ratio=0.3):
    # 動画の連結
    output_path, preview_clip, original_clip = merge_videos_with_timestamp(input_directory, output_file)
    if output_path is None:
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
        target_seconds = int(target_duration * 60)
        print(f"{duration_seconds} -> {target_seconds}")
        with open("prompts/prompt.md", "r") as f:
            prompt = f.read()
            prompt = prompt.format(
                duration=str(duration_seconds),
                target_duration=str(target_seconds)
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
        total_duration = sum([highlight.end_second - highlight.start_second for highlight in highlights.highlights])
        minutes = int(total_duration // 60)
        seconds = int(total_duration % 60)
        print(f"ハイライト動画の長さ: {minutes:02d}:{seconds:02d}")
        # ハイライト情報をJSONファイルとして保存
        output_json_path = Path(output_file).with_suffix('.json')
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(highlights.model_dump(), f, ensure_ascii=False, indent=2)
        print(f"ハイライト情報を保存しました: {output_json_path}")
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
    import argparse
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

    args = parser.parse_args()
    main(
        input_directory=args.input_dir,
        output_file=args.output_file,
        target_minutes=args.target_minutes,
        highlight_ratio=args.highlight_ratio,
    )
