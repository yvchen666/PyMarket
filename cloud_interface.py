# cloud_interface.py
import os
import shutil
import time
from abc import ABC, abstractmethod


class ICloudConnector(ABC):
    """
    云端连接器接口，定义了如何从云端获取插件信息和下载插件。
    """

    @abstractmethod
    def fetch_plugin_list(self):
        """
        从云端获取可用插件列表。
        应返回一个列表，每个元素是一个字典，包含插件元数据。
        例如:
        [
            {
                "id": "plugin_001",
                "name": "Hello World Python",
                "description": "一个简单的Python插件，打印Hello World。",
                "version": "1.0",
                "author": "AI Assistant",
                "script_type": "py",  # 'py' or 'sh'
                "download_url": "simulated://hello_world.py" # 模拟URL
            },
            # ...更多插件
        ]
        """
        pass

    @abstractmethod
    def download_plugin_script(self, plugin_info, local_save_path):
        """
        根据插件信息中的下载URL下载插件脚本。
        :param plugin_info: 包含插件元数据的字典 (如从 fetch_plugin_list 获取的)
        :param local_save_path: 本地保存脚本的完整路径
        :return: True如果下载成功，False如果失败
        """
        pass


class MockCloudConnector(ICloudConnector):
    def __init__(self, sample_plugin_dir="sample_plugins_for_cloud"):
        self.sample_plugin_dir = sample_plugin_dir
        # ... (确保目录和基础脚本创建) ...
        if not os.path.exists(self.sample_plugin_dir):
            os.makedirs(self.sample_plugin_dir)
            # 创建示例插件
            with open(os.path.join(self.sample_plugin_dir, "hello_world.py"), "w") as f:
                f.write("print('Hello from Python Plugin!')\n")
                f.write("import sys\n")
                f.write("print(f'Python version: {sys.version_info.major}.{sys.version_info.minor}')\n")

            with open(os.path.join(self.sample_plugin_dir, "list_files.sh"), "w") as f:
                f.write("#!/bin/bash\n")
                f.write("echo 'Listing files in current directory (from Shell Plugin):'\n")
                f.write("ls -la\n")
            if os.name != 'nt':
                os.chmod(os.path.join(self.sample_plugin_dir, "list_files.sh"), 0o755)

            # ---- 新增：带参数和输入的Python脚本 ----
            with open(os.path.join(self.sample_plugin_dir, "process_data.py"), "w") as f_proc:
                f_proc.write(
                    """
                    import sys
                    import argparse
                    import time
                    
                    print("Process Data Plugin Started.")
                    print(f"Arguments received: {sys.argv[1:]}")
                    
                    parser = argparse.ArgumentParser(description="Processes some data.")
                    parser.add_argument("--input-file", required=True, help="Path to the input data file.")
                    parser.add_argument("--output-file", default="output.txt", help="Path to save the output.")
                    parser.add_argument("--iterations", type=int, default=1, help="Number of processing iterations.")
                    
                    try:
                        args = parser.parse_args() # sys.argv[1:] is used by default
                    
                        print(f"Processing input file: {args.input_file}")
                        print(f"Output will be saved to: {args.output_file}")
                        print(f"Number of iterations: {args.iterations}")
                    
                        for i in range(args.iterations):
                            print(f"Iteration {i+1}/{args.iterations}...")
                            # Simulate work
                            time.sleep(0.5)
                    
                        # 尝试从标准输入读取一行（如果主程序关闭了stdin，这里会快速返回或出错）
                        try:
                            print("\\nAttempting to read a line from stdin (e.g., for a confirmation):")
                            user_confirmation = input("Type something and press Enter (will likely be EOF): ")
                            if user_confirmation: # Will be empty if stdin was closed
                                print(f"Stdin read: '{user_confirmation}'")
                            else:
                                print("Stdin was empty (EOF received as expected).")
                        except EOFError:
                            print("EOFError received when trying to read from stdin (as expected if stdin is closed).")
                        except Exception as e_input:
                            print(f"Error reading from stdin: {e_input}")
                    
                    
                        with open(args.output_file, "w") as outfile:
                            outfile.write(f"Processed {args.input_file} with {args.iterations} iterations.\\n")
                            outfile.write("This is a dummy output file from process_data.py plugin.\\n")
                    
                        print(f"Successfully processed and saved to {args.output_file}")
                    
                    except SystemExit: # Argparse calls sys.exit on --help or error
                        print("Argparse exited (e.g. due to --help or invalid arguments).")
                        # Depending on desired behavior, you might want to reraise or exit with a specific code
                        # For this example, we'll let it complete so the user sees the help message.
                    except Exception as e:
                        print(f"Error in process_data.py: {e}")
                        sys.exit(1) # Indicate failure
                    
                    print("Process Data Plugin Finished.")
                    """
                )
            # ---- 结束新增 ----

        self.plugins_metadata = [
            {
                "id": "py_hello_001", "name": "Hello World (Python)",
                "description": "一个简单的Python插件，打印 'Hello from Python Plugin!' 和Python版本。",
                "version": "1.0", "author": "Test User", "script_type": "py",
                "script_filename": "hello_world.py",
                "download_url": f"simulated://{self.sample_plugin_dir}/hello_world.py",
                "expected_args": []  # No arguments for this one
            },
            {
                "id": "sh_ls_002", "name": "List Files (Shell)",
                "description": "一个简单的Shell插件，列出当前目录的文件。",
                "version": "1.0", "author": "Test User", "script_type": "sh",
                "script_filename": "list_files.sh",
                "download_url": f"simulated://{self.sample_plugin_dir}/list_files.sh",
                "expected_args": [  # Shell script can also take args
                    {"name": "path_to_list", "type": "str",
                     "description": "Optional path to list (default: current dir)", "required": False}
                ]
            },
            # ---- 新增插件元数据 ----
            {
                "id": "py_process_data_003", "name": "Process Data (Python)",
                "description": "一个处理数据并尝试从stdin读取的Python插件。",
                "version": "1.1", "author": "AI Assistant", "script_type": "py",
                "script_filename": "process_data.py",
                "download_url": f"simulated://{self.sample_plugin_dir}/process_data.py",
                "expected_args": [
                    {"name": "input-file", "type": "str", "description": "Input data file path", "required": True},
                    {"name": "output-file", "type": "str", "description": "Output file path (default: output.txt)",
                     "required": False, "default": "output.txt"},
                    {"name": "iterations", "type": "int", "description": "Number of iterations (default: 1)",
                     "required": False, "default": "1"}
                ]
            }
            # ---- 结束新增 ----
        ]

    # ... (fetch_plugin_list and download_plugin_script methods remain the same) ...
    def fetch_plugin_list(self):
        print("MockCloudConnector: Fetching plugin list...")
        # time.sleep(0.5) # Simulate network delay
        return self.plugins_metadata

    def download_plugin_script(self, plugin_info, local_save_path):
        print(f"MockCloudConnector: 'Downloading' {plugin_info['name']} to {local_save_path}...")
        # time.sleep(1) # Simulate download delay

        source_script_name = plugin_info.get("script_filename")
        if not source_script_name:
            print(f"Error: Plugin info for {plugin_info['name']} missing 'script_filename'.")
            return False

        source_path = os.path.join(self.sample_plugin_dir, source_script_name)

        if not os.path.exists(source_path):
            print(f"Error: Source script {source_path} does not exist for plugin {plugin_info['name']}.")
            # Attempt to create it if it's one of the known sample scripts
            if plugin_info['name'] == "Process Data (Python)" and not os.path.exists(
                    os.path.join(self.sample_plugin_dir, "process_data.py")):
                self.__init__()  # Re-run init to create files if they were deleted
                if not os.path.exists(source_path): return False  # Still not there
            else:
                return False

        try:
            os.makedirs(os.path.dirname(local_save_path), exist_ok=True)
            shutil.copy(source_path, local_save_path)
            if plugin_info['script_type'] == 'sh' and os.name != 'nt':
                try:
                    os.chmod(local_save_path, 0o755)
                except Exception as e_chmod:
                    print(
                        f"MockCloudConnector: Warning - could not set execute permission for {local_save_path}: {e_chmod}")
            print(f"MockCloudConnector: Successfully 'downloaded' {plugin_info['name']}.")
            return True
        except Exception as e:
            print(f"MockCloudConnector: Error 'downloading' {plugin_info['name']}: {e}")
            return False