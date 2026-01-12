"""
视频翻译主程序
支持B站视频URL或本地视频文件,自动完成:
1. 视频下载(如果是URL)
2. 音频提取
3. 语音识别(ASR)
4. 文本翻译
5. 语音合成(TTS)
6. 音频替换
7. 输出翻译后的视频
"""

import sys
import time
from pathlib import Path
import argparse

# 配置标准输出使用 UTF-8 编码（解决 Windows GBK 编码问题）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 强制禁用缓冲区，实现实时输出
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# 配置日志系统 - 实时输出到终端
from common.logger import setup_logger, log_message

# 初始化日志系统
logger = setup_logger(
    name="VideoTranslate",
    level="INFO",
    log_file="video_translate.log",
)

# 使用log_message替代print进行格式化输出
def print_status(message: str):
    """打印状态消息（兼容旧代码）"""
    print(message)

from config import OUTPUT_DIR
from video_downloader import VideoDownloader
from audio_processor import AudioProcessor
from ai_services import AIServices
from speech_to_text import SpeechToText
from translate_text import DistributedTranslation
from cleanup_temp import cleanup_temp_files
from common.security import InputValidator, SecurityError, RegexValidator
from progress import TranslationProgress

# 翻译风格常量定义
VALID_TRANSLATION_STYLES = [
    "humorous",
    "serious",
    "educational",
    "entertainment",
    "news",
    "auto",
]


def normalize_style(style: str) -> str:
    """
    标准化翻译风格（大小写兼容）

    Args:
        style: 输入的风格名称

    Returns:
        标准化后的风格名称（小写）
    """
    if not isinstance(style, str):
        return "auto"

    # 转换为小写并匹配有效值
    style_lower = style.lower()

    # 精确匹配
    if style_lower in VALID_TRANSLATION_STYLES:
        return style_lower

    # 模糊匹配
    style_map = {
        "humor": "humorous",
        "humour": "humorous",
        "funny": "humorous",
        "serios": "serious",
        "series": "serious",
        "formal": "serious",
        "education": "educational",
        "edu": "educational",
        "entertain": "entertainment",
        "fun": "entertainment",
        "new": "news",
        "paper": "news",
        "a": "auto",
        "automatic": "auto",
    }

    if style_lower in style_map:
        return style_map[style_lower]

    # 无法匹配，返回默认值
    print(f"[警告] 无法识别的风格 '{style}'，使用默认风格 'auto'")
    return "auto"


def normalize_language(language: str) -> str:
    """
    标准化语言名称（大小写兼容）

    Args:
        language: 输入的语言名称

    Returns:
        标准化后的语言名称（首字母大写）
    """
    if not isinstance(language, str):
        return "English"

    # 去除首尾空格
    language = language.strip()

    # 空字符串返回默认值
    if not language:
        return "English"

    # 常见语言的别名映射（小写）
    language_map = {
        # 英语
        "english": "English",
        "en": "English",
        "eng": "English",

        # 日语
        "japanese": "Japanese",
        "ja": "Japanese",
        "jp": "Japanese",

        # 韩语
        "korean": "Korean",
        "ko": "Korean",
        "kr": "Korean",

        # 法语
        "french": "French",
        "fr": "French",

        # 德语
        "german": "German",
        "de": "German",

        # 西班牙语
        "spanish": "Spanish",
        "es": "Spanish",

        # 俄语
        "russian": "Russian",
        "ru": "Russian",

        # 意大利语
        "italian": "Italian",
        "it": "Italian",

        # 葡萄牙语
        "portuguese": "Portuguese",
        "pt": "Portuguese",

        # 中文
        "chinese": "Chinese",
        "zh": "Chinese",
        "cn": "Chinese",
    }

    language_lower = language.lower()

    # 直接匹配（首字母大写）
    if language[0].isupper() and language in ["English", "Japanese", "Korean", "French",
                                                   "German", "Spanish", "Russian", "Italian",
                                                   "Portuguese", "Chinese"]:
        return language

    # 查找映射
    if language_lower in language_map:
        return language_map[language_lower]

    # 如果已经是正确格式，直接返回
    if language in ["English", "Japanese", "Korean", "French", "German",
                    "Spanish", "Russian", "Italian", "Portuguese", "Chinese"]:
        return language

    # 无法识别，返回默认值
    print(f"[警告] 无法识别的语言 '{language}'，使用默认语言 'English'")
    return "English"


class VideoTranslator:
    """视频翻译器主类"""

    def __init__(self, translation_style: str = "auto", verbose: bool = False):
        """初始化视频翻译器

        Args:
            translation_style: 翻译风格，可选值：humorous, serious, educational, entertainment, news, auto
            verbose: 是否显示详细输出
        """
        # 初始化进度显示器
        self.progress = TranslationProgress(verbose=verbose)

        # 标准化翻译风格（大小写兼容）
        normalized_style = normalize_style(translation_style)
        if normalized_style != translation_style:
            print(f"[提示] 风格 '{translation_style}' 已标准化为 '{normalized_style}'")

        # 初始化AI服务
        self.ai_services = AIServices(normalized_style)

        # 初始化语音识别服务
        self.stt = SpeechToText()

        # 初始化分布式翻译服务
        self.translator = DistributedTranslation(normalized_style)

        print("\n" + "=" * 60)
        print("视频翻译系统 v1.1")
        print("支持: B站视频下载 | 语音识别 | 机器翻译 | 语音合成")
        print("新增: 多风格翻译模式")
        print("=" * 60 + "\n")

        # 显示当前翻译模式信息
        mode_info = self.ai_services.get_translation_mode_info()
        print(f"当前翻译模式: {mode_info['name']} ({mode_info['style']})")
        print(f"模式描述: {mode_info['description']}")
        print(f"模型参数: {mode_info['model_params']}")
        print()

    def translate_video(
        self, url_or_path: str, target_language: str, source_language: str = "auto"
    ) -> str:
        """
        翻译视频的完整流程

        Args:
            url_or_path: B站视频URL或本地视频文件路径
            target_language: 目标语言 (如: English, Japanese, Korean等)
            source_language: 源语言 (默认自动检测)

        Returns:
            翻译后的视频文件路径

        Raises:
            Exception: 处理过程中的任何错误
        """
        # 标准化目标语言（大小写兼容）
        normalized_language = normalize_language(target_language)
        if normalized_language != target_language:
            print(f"[提示] 语言 '{target_language}' 已标准化为 '{normalized_language}'")
        target_language = normalized_language

        start_time = time.time()

        try:
            # 步骤1: 准备视频文件
            self.progress.print_stage_header(1, "准备视频文件...")
            video_path, bv_id = VideoDownloader.prepare_video(url_or_path)
            self.progress.update_stage_progress(1, 100)
            if bv_id:
                self.progress.print_success(f"视频就绪: {video_path} (BV号: {bv_id})")
            else:
                self.progress.print_success(f"视频就绪: {video_path}")
            self.progress.close_stage(1)

            # 步骤2: 提取音频
            self.progress.print_stage_header(2, "提取原始音频...")
            original_audio = AudioProcessor.extract_audio(video_path)
            self.progress.update_stage_progress(2, 100)
            self.progress.print_success(f"音频提取完成: {original_audio}")
            self.progress.close_stage(2)

            # 步骤3: 语音识别
            self.progress.print_stage_header(3, "语音识别(ASR)...")
            self.progress.print_message("提示: 这可能需要几分钟,请耐心等待...")
            original_text = self.stt.recognize(original_audio)
            self.progress.update_stage_progress(3, 100)
            self.progress.print_success(f"识别完成,共 {len(original_text)} 字符")
            self.progress.close_stage(3)

            # 保存原文
            if bv_id:
                original_text_file = OUTPUT_DIR / f"{bv_id}_original.txt"
            else:
                video_name = Path(video_path).stem
                original_text_file = OUTPUT_DIR / f"{video_name}_original.txt"
            original_text_file.write_text(original_text, encoding="utf-8")
            self.progress.print_message(f"  原文已保存: {original_text_file}", verbose_only=True)

            # 步骤4: 文本翻译
            self.progress.print_stage_header(4, f"翻译文本 (目标语言: {target_language})...")

            # 使用分布式翻译（带质量评价和重试）
            translated_text, translation_score = self.translator.translate(
                original_text, target_language
            )

            self.progress.update_stage_progress(4, 100)
            self.progress.print_success(f"翻译完成,共 {len(translated_text)} 字符")
            self.progress.close_stage(4)

            # 如果有评分结果，显示评分信息
            if translation_score:
                self.progress.print_success(f"翻译质量评分: {translation_score.overall_score:.1f}/100")
                if translation_score.suggestions:
                    self.progress.print_message("改进建议:")
                    for i, suggestion in enumerate(
                        translation_score.suggestions[:3], 1
                    ):  # 只显示前3条建议
                        self.progress.print_message(f"  {i}. {suggestion}", verbose_only=True)

            # 保存译文
            if bv_id:
                translated_text_file = OUTPUT_DIR / f"{bv_id}_{target_language}.txt"
            else:
                video_name = Path(video_path).stem
                translated_text_file = (
                    OUTPUT_DIR / f"{video_name}_translated_{target_language}.txt"
                )
            translated_text_file.write_text(translated_text, encoding="utf-8")
            self.progress.print_message(f"  译文已保存: {translated_text_file}", verbose_only=True)

            # 如果有评分结果，保存评分报告
            if translation_score:
                from config import SCORING_RESULTS_DIR
                import json

                # 生成评分报告文件名
                if bv_id:
                    score_report_file = (
                        SCORING_RESULTS_DIR
                        / f"{bv_id}_{target_language}_score_report.json"
                    )
                else:
                    video_name = Path(video_path).stem
                    score_report_file = (
                        SCORING_RESULTS_DIR
                        / f"{video_name}_{target_language}_score_report.json"
                    )

                # 准备评分报告数据
                score_report = {
                    "video_info": {
                        "bv_id": bv_id,
                        "video_path": video_path,
                        "source_language": source_language,
                        "target_language": target_language,
                    },
                    "translation_score": {
                        "overall_score": translation_score.overall_score,
                        "fluency": translation_score.fluency,
                        "completeness": translation_score.completeness,
                        "consistency": translation_score.consistency,
                        "accuracy": translation_score.accuracy,
                        "style_adaptation": translation_score.style_adaptation,
                        "cultural_adaptation": translation_score.cultural_adaptation,
                        "suggestions": translation_score.suggestions,
                        "detailed_feedback": translation_score.detailed_feedback,
                    },
                    "timestamp": int(time.time()),
                }

                # 保存评分报告
                with open(score_report_file, "w", encoding="utf-8") as f:
                    json.dump(score_report, f, ensure_ascii=False, indent=2)
                self.progress.print_message(f"  评分报告已保存: {score_report_file}", verbose_only=True)

            # 步骤5: 语音合成
            self.progress.print_stage_header(5, "语音合成(TTS)...")
            self.progress.print_message("提示: 正在生成新的配音...")
            new_audio = self.ai_services.text_to_speech(
                translated_text, language=target_language
            )
            self.progress.update_stage_progress(5, 100)
            self.progress.print_success(f"语音合成完成: {new_audio}")
            self.progress.close_stage(5)

            # 步骤6: 替换音频
            self.progress.print_stage_header(6, "合成最终视频...")
            self.progress.print_message("提示: 正在合成视频,这可能需要几分钟...")
            output_video = AudioProcessor.replace_audio(
                video_path, new_audio, bv_id=bv_id, target_language=target_language
            )
            self.progress.update_stage_progress(6, 100)
            self.progress.print_success("视频合成完成!")
            self.progress.close_stage(6)

            # 完成
            elapsed_time = time.time() - start_time
            print("\n" + "=" * 60)
            self.progress.print_success("翻译完成!")
            print(f"  总耗时: {elapsed_time:.1f} 秒 ({elapsed_time / 60:.1f} 分钟)")
            print(f"  输出视频: {output_video}")
            print(f"  原文文本: {original_text_file}")
            print(f"  译文文本: {translated_text_file}")
            print("=" * 60 + "\n")

            # 自动清理临时文件
            print("\n[清理临时文件]")
            try:
                cleanup_temp_files(keep_video_path=str(output_video))
            except Exception as e:
                self.progress.print_warning(f"临时文件清理失败: {e}")

            return output_video

        except Exception as e:
            self.progress.print_error(str(e))
            raise


def main():
    """主函数 - 命令行接口"""
    parser = argparse.ArgumentParser(
        description="视频翻译系统 - 支持B站视频URL或本地视频文件翻译",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 翻译B站视频为英文（自动风格）
    python main.py "https://www.bilibili.com/video/BVxxxxxxxxx" English
    
    # 翻译本地视频为日文（幽默风格）
    python main.py "video.mp4" Japanese --style humorous
    
    # 翻译教育视频为英文（教育风格）
    python main.py "education_video.mp4" English --style educational --verbose
    
    # 查看帮助信息
    python main.py --help
    
    # 查看版本信息
    python main.py --version

支持的语言:
    Chinese, English, Japanese, Korean, Spanish, French, 
    German, Russian, Italian, Portuguese 等92种语言
    
翻译风格:
    humorous    - 幽默风格，保留原视频的幽默感和轻松氛围
    serious     - 正经风格，适用于正式、严肃的内容
    educational - 教育风格，适用于教学、科普类内容
    entertainment- 娱乐风格，适用于娱乐、综艺类内容
    news        - 新闻风格，适用于新闻、资讯类内容
    auto        - 自动检测，根据内容自动选择最适合的风格（默认）
    
注意: 源语言将自动识别，无需手动指定
        """
    )

    parser.add_argument(
        "url_or_path",
        help="B站视频URL或本地视频文件路径"
    )
    
    parser.add_argument(
        "target_language",
        help="目标语言 (如: English, Japanese, Korean等)"
    )
    
    parser.add_argument(
        "--style", "-s",
        choices=["humorous", "serious", "educational", "entertainment", "news", "auto"],
        default="auto",
        help="翻译风格 (默认: auto)"
    )
    
    parser.add_argument(
        "--source-language",
        default="auto",
        help="源语言 (默认: auto - 自动识别)"
    )
    
    parser.add_argument(
        "--config", "-c",
        help="配置文件路径"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.1"
    )

    args = parser.parse_args()

    url_or_path = args.url_or_path
    target_language = args.target_language
    source_language = args.source_language
    translation_style = args.style
    verbose = args.verbose

    # 使用InputValidator进行安全验证
    try:
        # 1. 编码格式验证 - 确保参数是有效的UTF-8字符串
        try:
            url_or_path.encode("utf-8")
            target_language.encode("utf-8")
            translation_style.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("参数包含无效的字符编码，请使用UTF-8编码")

        # 2. 特殊字符过滤 - 防止命令注入
        dangerous_chars = ["|", "&", ";", "$", "`", "(", ")", "<", ">", '"', "'"]
        for char in dangerous_chars:
            if char in url_or_path:
                raise ValueError(f"URL/路径包含危险字符: {char}")

        # 3. URL/路径长度验证
        url_or_path = InputValidator.validate_url_length(url_or_path, max_length=1000)

        # 4. 语言参数标准化（大小写兼容）
        target_language = normalize_language(target_language)
        source_language = normalize_language(source_language)

        # 5. 翻译风格参数标准化（大小写兼容）
        translation_style = normalize_style(translation_style)

        # 6. 正则表达式输入长度验证（防止ReDoS）
        RegexValidator.validate_input_length_for_regex(url_or_path, max_length=500)

    except ValueError as e:
        print(f"参数验证失败: {e}")
        sys.exit(1)
    except SecurityError as e:
        print(f"安全检查失败: {e}")
        sys.exit(1)

    try:
        # 创建翻译器并执行
        translator = VideoTranslator(translation_style, verbose=verbose)
        output_video = translator.translate_video(
            url_or_path, target_language, source_language
        )

        print(f"\n成功! 翻译后的视频已保存到: {output_video}")

    except KeyboardInterrupt:
        print("\n\n用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n处理失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
