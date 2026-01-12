"""
交互式配置向导
帮助用户快速完成初始配置
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from http.client import HTTPSConnection
import urllib.request
import urllib.error

# 配置标准输出使用 UTF-8 编码（解决 Windows GBK 编码问题）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


class ConfigWizard:
    """配置向导类"""

    def __init__(self, config_dir: Optional[Path] = None):
        """初始化配置向导

        Args:
            config_dir: 配置文件目录，默认为项目根目录
        """
        if config_dir is None:
            self.config_dir = Path(__file__).parent
        else:
            self.config_dir = Path(config_dir)

        self.env_file = self.config_dir / ".env"
        self.env_example_file = self.config_dir / ".env.example"
        self.config_file = self.config_dir / "user_config.json"

        self.api_keys = {
            "DASHSCOPE_API_KEY": {
                "description": "阿里云DashScope API密钥（用于ASR、TTS、翻译）",
                "required": True,
                "test_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                "env_var": "DASHSCOPE_API_KEY"
            },
            "ZHIPU_API_KEY": {
                "description": "智谱AI API密钥（用于分布式翻译的glm-4.5-air模型）",
                "required": False,
                "test_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "env_var": "ZHIPU_API_KEY"
            },
            "DEEPSEEK_API_KEY": {
                "description": "DeepSeek API密钥（用于分布式翻译的deepseek-chat模型）",
                "required": False,
                "test_url": "https://api.deepseek.com/v1/chat/completions",
                "env_var": "DEEPSEEK_API_KEY"
            },
            "OSS_ACCESS_KEY_ID": {
                "description": "阿里云OSS访问密钥ID",
                "required": False,
                "test_url": "https://oss-cn-hangzhou.aliyuncs.com",
                "env_var": "OSS_ACCESS_KEY_ID"
            },
            "OSS_ACCESS_KEY_SECRET": {
                "description": "阿里云OSS访问密钥Secret",
                "required": False,
                "test_url": "https://oss-cn-hangzhou.aliyuncs.com",
                "env_var": "OSS_ACCESS_KEY_SECRET"
            },
            "OSS_BUCKET_NAME": {
                "description": "阿里云OSS存储桶名称",
                "required": False,
                "test_url": None,
                "env_var": "OSS_BUCKET_NAME"
            }
        }

    def detect_api_keys(self) -> Dict[str, Optional[str]]:
        """检测已配置的API密钥

        Returns:
            API密钥状态字典，key为密钥名称，value为密钥值（未配置时为None）
        """
        detected = {}
        for key_name, key_info in self.api_keys.items():
            env_var = key_info["env_var"]
            value = os.getenv(env_var)
            detected[key_name] = value

        return detected

    def test_connection(self, api_key: str, test_url: str, timeout: int = 10) -> Tuple[bool, str]:
        """测试API连接

        Args:
            api_key: API密钥
            test_url: 测试URL
            timeout: 超时时间（秒）

        Returns:
            (是否成功, 消息)
        """
        try:
            request = urllib.request.Request(
                test_url,
                method="GET",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if 200 <= response.status < 300:
                    return True, f"连接成功 (HTTP {response.status})"
                else:
                    return False, f"连接失败 (HTTP {response.status})"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "API密钥无效"
            elif e.code == 403:
                return False, "API密钥权限不足"
            else:
                return False, f"HTTP错误: {e.code}"
        except urllib.error.URLError as e:
            return False, f"网络错误: {str(e.reason)}"
        except Exception as e:
            return False, f"未知错误: {str(e)}"

    def generate_env_file(self, api_keys: Dict[str, str], overwrite: bool = False) -> Path:
        """生成.env文件

        Args:
            api_keys: API密钥字典
            overwrite: 是否覆盖已有文件

        Returns:
            生成的.env文件路径
        """
        if self.env_file.exists() and not overwrite:
            raise FileExistsError(f".env文件已存在: {self.env_file}")

        lines = ["# VideoTranslate 配置文件", "# 由配置向导自动生成"]
        lines.append("")

        for key_name, key_info in self.api_keys.items():
            value = api_keys.get(key_name, "")
            if value:
                lines.append(f"{key_info['env_var']}={value}")
            elif key_info["required"]:
                lines.append(f"{key_info['env_var']}=")

        self.env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self.env_file

    def generate_config_json(self, config: Dict, overwrite: bool = False) -> Path:
        """生成user_config.json配置文件

        Args:
            config: 配置字典
            overwrite: 是否覆盖已有文件

        Returns:
            生成的配置文件路径
        """
        if self.config_file.exists() and not overwrite:
            raise FileExistsError(f"配置文件已存在: {self.config_file}")

        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        return self.config_file

    def print_header(self, title: str):
        """打印标题

        Args:
            title: 标题内容
        """
        print("\n" + "=" * 60)
        print(f"  {title}")
        print("=" * 60 + "\n")

    def print_status(self, key_name: str, value: Optional[str], required: bool):
        """打印配置状态

        Args:
            key_name: 密钥名称
            value: 密钥值
            required: 是否必需
        """
        status_icon = "✓" if value else "✗"
        req_icon = "*" if required else ""
        print(f"  {status_icon} {key_name}{req_icon}: {'已配置' if value else '未配置'}")

    def run(self):
        """运行配置向导"""
        self.print_header("VideoTranslate 配置向导")
        print("欢迎使用VideoTranslate配置向导！")
        print("本向导将帮助您配置系统所需的API密钥。\n")

        print("步骤 1: 检测现有配置")
        print("-" * 60)
        detected = self.detect_api_keys()

        for key_name, key_info in self.api_keys.items():
            self.print_status(key_name, detected[key_name], key_info["required"])

        print()

        print("步骤 2: 配置API密钥")
        print("-" * 60)

        api_keys_config = {}
        for key_name, key_info in self.api_keys.items():
            current_value = detected[key_name]
            required = key_info["required"]
            description = key_info["description"]

            print(f"\n配置: {key_name}")
            print(f"说明: {description}")
            print(f"必需: {'是' if required else '否（可选）'}")

            if current_value:
                print(f"当前值: {'*' * len(current_value)}")
                change = input(f"是否修改? [y/N]: ").strip().lower()
                if change != 'y':
                    api_keys_config[key_name] = current_value
                    continue

            while True:
                new_value = input("请输入密钥 (留空跳过): ").strip()
                if not new_value:
                    if required:
                        print("此密钥为必需项，请输入有效值")
                        continue
                    else:
                        api_keys_config[key_name] = ""
                        print("已跳过\n")
                        break

                if len(new_value) < 10:
                    print("警告: 密钥长度似乎过短，请确认")
                    confirm = input("继续使用此密钥? [y/N]: ").strip().lower()
                    if confirm != 'y':
                        continue

                api_keys_config[key_name] = new_value
                print("已保存\n")
                break

        print("\n步骤 3: 测试API连接")
        print("-" * 60)

        test_results = {}
        for key_name, key_info in self.api_keys.items():
            value = api_keys_config.get(key_name)
            if not value:
                continue

            test_url = key_info.get("test_url")
            if not test_url:
                print(f"{key_name}: 跳过连接测试")
                test_results[key_name] = (None, "无测试URL")
                continue

            print(f"测试 {key_name}...", end=" ", flush=True)
            success, message = self.test_connection(value, test_url)
            test_results[key_name] = (success, message)

            if success:
                print(f"✓ {message}")
            else:
                print(f"✗ {message}")

        print()

        print("步骤 4: 生成配置文件")
        print("-" * 60)

        try:
            env_path = self.generate_env_file(api_keys_config, overwrite=True)
            print(f"✓ .env文件已生成: {env_path}")
        except FileExistsError as e:
            print(f"✗ {e}")
            overwrite = input("是否覆盖现有文件? [y/N]: ").strip().lower()
            if overwrite == 'y':
                env_path = self.generate_env_file(api_keys_config, overwrite=True)
                print(f"✓ .env文件已更新: {env_path}")

        user_config = {
            "configured_at": "",
            "api_keys": {k: bool(v) for k, v in api_keys_config.items()},
            "test_results": {k: {"success": v[0], "message": v[1]} for k, v in test_results.items()}
        }

        from datetime import datetime
        user_config["configured_at"] = datetime.now().isoformat()

        try:
            config_path = self.generate_config_json(user_config, overwrite=True)
            print(f"✓ 配置文件已生成: {config_path}")
        except FileExistsError as e:
            print(f"✗ {e}")

        print()

        print("配置完成!")
        print("-" * 60)
        print("\n下一步:")
        print("1. 重新加载终端或运行: source .env (Linux/Mac) 或 setenv (Windows)")
        print("2. 运行: python main.py --help 查看使用说明")
        print("3. 示例: python main.py \"https://www.bilibili.com/video/BVxxxxx\" English\n")


def config_wizard():
    """配置向导入口函数"""
    wizard = ConfigWizard()
    wizard.run()


if __name__ == "__main__":
    config_wizard()
