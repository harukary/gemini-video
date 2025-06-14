from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
from pydantic import BaseModel, Field

class Narration(BaseModel):
    narration: str = Field(..., description="ナレーション")
    start_second: float = Field(..., description="開始秒数")
    end_second: float = Field(..., description="終了秒数")

class VideoHighlight(BaseModel):
    start_second: float = Field(..., description="開始秒数")
    end_second: float = Field(..., description="終了秒数")
    narration: list[Narration] = Field(..., description="ナレーション")

def debug_clip_info(clip, name="clip"):
    """クリップの情報をデバッグ出力"""
    try:
        print(f"\n{name}の情報:")
        print(f"duration: {clip.duration}")
        print(f"size: {clip.size}")
        print(f"fps: {clip.fps}")
    except Exception as e:
        print(f"{name}の情報取得に失敗: {e}")

def create_highlight_video(video_clip, output_path, highlights):
    clips = []
    text_clips = []
    final_video = None
    
    try:
        print("\n=== 入力ビデオの情報 ===")
        debug_clip_info(video_clip, "入力ビデオ")
        
        # 最初のクリップのみをテスト
        print("\n=== クリップの切り出し ===")
        clip = video_clip.subclip(0, 5)
        debug_clip_info(clip, "切り出したクリップ")
        clips.append(clip)
        
        print("\n=== クリップの連結 ===")
        final_video = concatenate_videoclips(clips)
        debug_clip_info(final_video, "連結後のビデオ")
        
        print("\n=== テキストクリップの作成 ===")
        text_clip = TextClip(
            "テストナレーション",
            fontsize=24,
            font='/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc',
            color='white',
            bg_color='rgba(0,0,0,0.5)',
            size=(final_video.w, None),
            method='caption'
        ).set_position(('center', 'bottom')).set_duration(5).set_start(0)
        text_clips.append(text_clip)
        
        print("\n=== 最終的な合成 ===")
        final_composite = CompositeVideoClip([final_video] + text_clips)
        debug_clip_info(final_composite, "最終合成ビデオ")
        
        output_path = str(Path(output_path).with_suffix(".mp4").with_stem(Path(output_path).stem + "_test"))
        print(f"\n=== 動画の書き出し: {output_path} ===")
        final_composite.write_videofile(
            output_path,
            threads=4,
            codec='libx264',
            audio_codec='aac',
            fps=30
        )
        print("動画の書き出しが完了しました")
        return output_path
        
    except Exception as e:
        import traceback
        print(f"\nエラーが発生しました: {e}")
        print("詳細なエラー情報:")
        print(traceback.format_exc())
        return None
        
    finally:
        print("\n=== クリーンアップ処理 ===")
        # クリップのクリーンアップ
        for i, clip in enumerate(clips):
            try:
                print(f"クリップ {i} をクローズ中...")
                clip.close()
            except Exception as e:
                print(f"クリップ {i} のクローズに失敗: {e}")
                
        for i, text_clip in enumerate(text_clips):
            try:
                print(f"テキストクリップ {i} をクローズ中...")
                text_clip.close()
            except Exception as e:
                print(f"テキストクリップ {i} のクローズに失敗: {e}")
                
        if final_video:
            try:
                print("最終ビデオをクローズ中...")
                final_video.close()
            except Exception as e:
                print(f"最終ビデオのクローズに失敗: {e}")

def test_highlight():
    video_clip = None
    try:
        input_video = "videos/disney_2024.mp4"  # テスト用の入力動画
        output_path = "videos/test_output.mp4"
        
        print("=== 動画を読み込み中... ===")
        video_clip = VideoFileClip(input_video)
        debug_clip_info(video_clip, "読み込んだビデオ")
        
        highlight = VideoHighlight(
            start_second=0,
            end_second=5,
            narration=[
                Narration(
                    narration="テストナレーション",
                    start_second=0,
                    end_second=5
                )
            ]
        )
        
        result = create_highlight_video(video_clip, output_path, [highlight])
        print(f"\nテスト結果: {result}")
        
    except Exception as e:
        import traceback
        print(f"\nテスト中にエラーが発生: {e}")
        print("詳細なエラー情報:")
        print(traceback.format_exc())
    finally:
        if video_clip:
            try:
                print("\n入力ビデオをクローズ中...")
                video_clip.close()
            except Exception as e:
                print(f"入力ビデオのクローズに失敗: {e}")

if __name__ == "__main__":
    test_highlight() 