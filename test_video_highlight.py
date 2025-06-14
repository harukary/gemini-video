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

def create_highlight_video(video_clip, output_path, highlights):
    clips = []
    try:
        # テスト用の単純なハイライト
        clip = video_clip.subclip(0, 5)  # 最初の5秒を切り出し
        clips.append(clip)
        
        final_video = concatenate_videoclips(clips)
        
        # テスト用の単純なテキスト
        text_clip = TextClip(
            "テストナレーション",
            fontsize=24,
            font='/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc',
            color='white',
            bg_color='rgba(0,0,0,0.5)',
            size=(final_video.w, None),
            method='caption'
        ).set_position(('center', 'bottom')).set_duration(5)
        
        final_video = CompositeVideoClip([final_video, text_clip])
        output_path = str(Path(output_path).with_suffix(".mp4").with_stem(Path(output_path).stem + "_test"))
        
        print("動画の書き出しを開始します...")
        final_video.write_videofile(
            output_path,
            threads=4,
        )
        print("動画の書き出しが完了しました")
        return output_path
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return None
    finally:
        for clip in clips:
            try:
                clip.close()
            except:
                pass

def test_highlight():
    try:
        # テスト用の入力動画
        input_video = "videos/tokyo.mp4"
        output_path = "videos/test_output.mp4"
        
        print("動画を読み込み中...")
        video_clip = VideoFileClip(input_video)
        
        # テスト用のハイライトデータ
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
        print(f"テスト結果: {result}")
        
    except Exception as e:
        print(f"テスト中にエラーが発生: {e}")
    finally:
        if 'video_clip' in locals():
            video_clip.close()

if __name__ == "__main__":
    test_highlight() 