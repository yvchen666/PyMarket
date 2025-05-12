# plugin_manager.py
import os
import subprocess
import sys
import json
import traceback  # For detailed exception logging

# 本地插件状态存储文件名
LOCAL_PLUGIN_DB_FILE = "local_plugins.json"


class Plugin:
    """封装插件信息的类"""

    def __init__(self, id, name, description, version, author, script_type, download_url, script_filename,
                 expected_args=None):
        self.id = id
        self.name = name
        self.description = description
        self.version = version
        self.author = author
        self.script_type = script_type  # 'py' or 'sh'
        self.download_url = download_url
        self.script_filename = script_filename
        self.expected_args = expected_args if expected_args else []  # 例如: [{"name": "input_file", "type": "str", "description": "输入文件路径", "required": True, "default": "default.txt"}]

        self.local_path = None
        self.is_downloaded = False
        self.status_message = "Available"

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            version=data['version'],
            author=data['author'],
            script_type=data['script_type'],
            download_url=data['download_url'],
            script_filename=data.get('script_filename', f"{data['id']}.{data['script_type']}"),
            expected_args=data.get('expected_args')
        )

    def to_dict_for_db(self):
        """用于存储到本地DB的表示"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "script_type": self.script_type,
            "download_url": self.download_url,
            "script_filename": self.script_filename,
            "local_path": self.local_path,
            "is_downloaded": self.is_downloaded,
            "expected_args": self.expected_args  # 保存参数定义
        }


class PluginManager:
    def __init__(self, cloud_connector, local_plugins_dir="plugins"):
        self.cloud_connector = cloud_connector
        self.local_plugins_dir = local_plugins_dir
        self.available_plugins = {}  # plugin_id -> Plugin object
        self.local_db_path = os.path.join(self.local_plugins_dir, LOCAL_PLUGIN_DB_FILE)

        if not os.path.exists(self.local_plugins_dir):
            os.makedirs(self.local_plugins_dir)

        self._load_local_plugin_db()

    def _load_local_plugin_db(self):
        try:
            if os.path.exists(self.local_db_path):
                with open(self.local_db_path, 'r') as f:
                    local_plugins_data = json.load(f)
                for plugin_id, data in local_plugins_data.items():
                    plugin = Plugin.from_dict(data)  # 使用原始元数据创建
                    plugin.local_path = data.get('local_path')
                    plugin.is_downloaded = data.get('is_downloaded', False)
                    if plugin.is_downloaded and plugin.local_path and os.path.exists(plugin.local_path):
                        plugin.status_message = "Downloaded"
                    else:  # 如果记录存在但文件丢失，标记为未下载
                        plugin.is_downloaded = False
                        plugin.local_path = None
                        plugin.status_message = "Available (file missing or metadata changed)"
                    self.available_plugins[plugin.id] = plugin
                print(f"Loaded {len(self.available_plugins)} plugins from local DB.")
        except Exception as e:
            print(f"Error loading local plugin DB: {e}")
            self.available_plugins = {}  # 出错则清空

    def _save_local_plugin_db(self):
        data_to_save = {}
        for plugin_id, plugin_obj in self.available_plugins.items():
            data_to_save[plugin_id] = plugin_obj.to_dict_for_db()
        try:
            with open(self.local_db_path, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            print("Saved local plugin DB.")
        except Exception as e:
            print(f"Error saving local plugin DB: {e}")

    def discover_plugins(self):
        print("Discovering plugins...")
        remote_plugin_data_list = self.cloud_connector.fetch_plugin_list()
        if remote_plugin_data_list is None:
            print("Failed to fetch plugin list from cloud.")
            self._save_local_plugin_db()  # Still save to update any local status changes
            return list(self.available_plugins.values())

        newly_discovered_count = 0
        updated_count = 0

        # remote_ids = {p_data['id'] for p_data in remote_plugin_data_list} # For removing old ones

        for plugin_data in remote_plugin_data_list:
            plugin_id = plugin_data['id']
            if plugin_id in self.available_plugins:
                existing_plugin = self.available_plugins[plugin_id]
                # Update all relevant fields from cloud
                existing_plugin.name = plugin_data['name']
                existing_plugin.description = plugin_data['description']
                existing_plugin.version = plugin_data['version']
                existing_plugin.author = plugin_data['author']
                existing_plugin.script_type = plugin_data['script_type']
                existing_plugin.download_url = plugin_data['download_url']
                new_script_filename = plugin_data.get('script_filename', f"{plugin_id}.{plugin_data['script_type']}")
                existing_plugin.expected_args = plugin_data.get('expected_args', [])  # Update expected_args

                # If script filename changed, existing local_path might be invalid
                if existing_plugin.script_filename != new_script_filename and existing_plugin.is_downloaded:
                    print(f"Script filename changed for {existing_plugin.name}. Marking as not downloaded.")
                    existing_plugin.is_downloaded = False
                    existing_plugin.local_path = None  # Old path is no longer valid for this metadata
                    existing_plugin.status_message = "Available (filename changed)"
                existing_plugin.script_filename = new_script_filename

                # Verify downloaded file still exists if marked as downloaded
                if existing_plugin.is_downloaded:
                    if not existing_plugin.local_path or not os.path.exists(existing_plugin.local_path):
                        existing_plugin.is_downloaded = False
                        existing_plugin.local_path = None
                        existing_plugin.status_message = "Available (file missing)"
                updated_count += 1
            else:
                plugin = Plugin.from_dict(plugin_data)
                self.available_plugins[plugin_id] = plugin
                newly_discovered_count += 1

        if newly_discovered_count > 0:
            print(f"Discovered {newly_discovered_count} new plugins from cloud.")
        if updated_count > 0:
            print(f"Updated metadata for {updated_count} existing plugins.")

        self._save_local_plugin_db()
        return list(self.available_plugins.values())

    def get_plugin_by_id(self, plugin_id):
        return self.available_plugins.get(plugin_id)

    def download_plugin(self, plugin_id):
        plugin = self.get_plugin_by_id(plugin_id)
        if not plugin:
            print(f"Plugin with ID {plugin_id} not found.")
            return False, "Plugin not found"

        expected_local_path = os.path.join(self.local_plugins_dir, plugin.script_filename)
        if plugin.is_downloaded and plugin.local_path == expected_local_path and os.path.exists(plugin.local_path):
            print(f"Plugin {plugin.name} already downloaded and file is current.")
            plugin.status_message = "Downloaded"
            self._save_local_plugin_db()
            return True, "Already downloaded"

        plugin.status_message = "Downloading..."

        local_save_path = os.path.join(self.local_plugins_dir, plugin.script_filename)

        plugin_info_for_download = {
            "id": plugin.id, "name": plugin.name, "script_type": plugin.script_type,
            "download_url": plugin.download_url, "script_filename": plugin.script_filename
        }

        success = self.cloud_connector.download_plugin_script(plugin_info_for_download, local_save_path)

        if success:
            plugin.local_path = local_save_path
            plugin.is_downloaded = True
            plugin.status_message = "Downloaded"
            print(f"Plugin {plugin.name} downloaded successfully to {local_save_path}")
        else:
            plugin.status_message = "Download failed"
            if os.path.exists(local_save_path):
                try:
                    os.remove(local_save_path)
                except Exception as e_rem:
                    print(f"Could not remove partially downloaded file {local_save_path}: {e_rem}")
            plugin.local_path = None
            plugin.is_downloaded = False
            print(f"Failed to download plugin {plugin.name}")

        self._save_local_plugin_db()
        return success, plugin.status_message

    def run_plugin(self, plugin_id, output_callback=None, args_for_plugin=None):  # Added args_for_plugin
        plugin = self.get_plugin_by_id(plugin_id)
        if not plugin:
            return False, "Plugin not found."
        if not plugin.is_downloaded or not plugin.local_path or not os.path.exists(plugin.local_path):
            if plugin.is_downloaded and plugin.local_path and not os.path.exists(plugin.local_path):
                msg = f"Plugin script file missing: {plugin.local_path}. Please re-download."
                plugin.status_message = "File missing"
                plugin.is_downloaded = False  # Mark as not properly downloaded
                self._save_local_plugin_db()
                return False, msg
            return False, "Plugin not downloaded or file missing."

        if args_for_plugin is None:  # Ensure it's a list
            args_for_plugin = []

        plugin.status_message = "Running..."

        script_filename_only = os.path.basename(plugin.local_path)
        plugin_dir = os.path.dirname(plugin.local_path)

        command = []
        if plugin.script_type == 'py':
            command = [sys.executable, script_filename_only] + args_for_plugin  # Add arguments
        elif plugin.script_type == 'sh':
            if os.name != 'nt':  # On Unix-like systems
                if not os.access(plugin.local_path, os.X_OK):
                    try:
                        os.chmod(plugin.local_path, 0o755)  # Make it executable
                        if output_callback: output_callback(f"INFO: Made {script_filename_only} executable.\n")
                    except Exception as e:
                        err_msg = f"Could not make script {script_filename_only} executable: {e}"
                        if output_callback: output_callback(f"ERROR: {err_msg}\n")
                        plugin.status_message = "Execution permission error"
                        self._save_local_plugin_db()
                        return False, err_msg
            command = [f"./{script_filename_only}"] + args_for_plugin  # Add arguments
        else:
            plugin.status_message = "Unsupported script type"
            self._save_local_plugin_db()
            return False, f"Unsupported script type: {plugin.script_type}"

        print(f"Running command: '{' '.join(command)}' in directory: '{plugin_dir}'")
        try:
            popen_kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'stdin': subprocess.PIPE,  # Crucial for sending input, even if not used by all scripts
                'cwd': plugin_dir
            }
            if sys.version_info >= (3, 7):
                popen_kwargs['text'] = True
                popen_kwargs['encoding'] = 'utf-8'  # Be explicit with encoding
            else:
                popen_kwargs['universal_newlines'] = True

            process = subprocess.Popen(command, **popen_kwargs)

            stdout_str = ""
            stderr_str = ""

            # --- Handling stdin ---
            # For scripts that might need immediate input (e.g. Python's input() called early)
            # If we have specific input to send, we'd do it here via process.stdin.write()
            # For general interactive input, it's complex.
            # For now, we'll just close stdin if no specific input is provided.
            # This tells the script there's no more input coming from this pipe.
            # If a script truly needs interactive input, this setup will likely make it hang or error.
            process.stdin.close()  # Close stdin to signal no input, unless we plan to send some.

            if output_callback:
                output_callback(f"--- Running {plugin.name} ---\n")

                # Read stdout (non-blocking or in threads for true simultaneous read with stderr)
                for line in iter(process.stdout.readline, ''):
                    stdout_str += line
                    if output_callback: output_callback(line)

                # Read stderr
                for line in iter(process.stderr.readline, ''):
                    stderr_str += line
                    if output_callback: output_callback(f"ERROR: {line}")

            # Wait for process to complete and get return code
            return_code = process.wait()

            # If no callback, read any remaining output after wait() (though iter should get most)
            if not output_callback:
                # communicate() after iter and wait can be problematic.
                # It's better to rely on what iter captured or what process.stdout.read() would give.
                # For simplicity, if no callback, we'll assume iter captured enough for debug.
                # stdout_final, stderr_final = process.communicate() # This would be if iter wasn't used.
                # stdout_str += stdout_final if stdout_final else ""
                # stderr_str += stderr_final if stderr_final else ""
                pass  # stdout_str and stderr_str will hold what iter got (which is nothing if no callback)

            if return_code == 0:
                plugin.status_message = "Run successful"
                success_msg = f"Plugin executed successfully (exit code {return_code})."
                if output_callback:
                    output_callback(f"--- {plugin.name} finished successfully (exit code {return_code}) ---\n")
            else:
                plugin.status_message = f"Run failed (code {return_code})"
                error_message = f"Plugin execution failed with code {return_code}.\n"
                if stderr_str.strip():
                    error_message += f"Error Output:\n{stderr_str.strip()}"
                elif stdout_str.strip():
                    error_message += f"Output (may contain error):\n{stdout_str.strip()}"
                else:
                    error_message += "No explicit error output captured on stderr/stdout."
                if output_callback:
                    output_callback(f"--- {plugin.name} failed (exit code {return_code}) ---\n")
                success_msg = error_message.strip()  # For the worker result

            # Debug printing
            if stdout_str.strip(): print(f"DEBUG Full STDOUT for {plugin.name}:\n{stdout_str.strip()}")
            if stderr_str.strip(): print(f"DEBUG Full STDERR for {plugin.name}:\n{stderr_str.strip()}")

            return return_code == 0, success_msg

        except FileNotFoundError:
            plugin.status_message = "Execution failed (command not found)"
            err_msg = f"Error running plugin {plugin.name}: Command or script not found. Command: {' '.join(command)}, CWD: {plugin_dir}"
            if output_callback: output_callback(err_msg + "\n")
            print(err_msg)
            return False, err_msg
        except Exception as e:
            plugin.status_message = f"Execution error"
            err_msg = f"An error occurred while running plugin {plugin.name} (Cmd: {' '.join(command)}, CWD: {plugin_dir}): {type(e).__name__}: {e}"
            if output_callback: output_callback(err_msg + "\n")
            print(err_msg)
            traceback.print_exc()
            return False, err_msg
        finally:
            # Ensure process streams are closed if process object exists
            if 'process' in locals() and process:
                if process.stdout and not process.stdout.closed:
                    process.stdout.close()
                if process.stderr and not process.stderr.closed:
                    process.stderr.close()
                # stdin was closed earlier
            self._save_local_plugin_db()