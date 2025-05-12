# main_app.py
import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QLabel, QTextEdit,
    QSplitter, QGroupBox, QFormLayout, QMessageBox, QDialog,
    QLineEdit, QDialogButtonBox, QSpinBox, QFileDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont

from cloud_interface import MockCloudConnector  # 使用模拟接口
from plugin_manager import PluginManager, Plugin  # Plugin class is used for type hinting


# --- Worker Thread for long tasks (Download/Run) ---
class Worker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str)  # For text updates from plugin execution
    result = pyqtSignal(bool, str, object)  # success, message, plugin_object (optional)

    def __init__(self, task_callable, *args, **kwargs):
        super().__init__()
        self.task_callable = task_callable
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            success, message, plugin_obj = self.task_callable(*self.args, **self.kwargs)
            self.result.emit(success, message, plugin_obj)
        except Exception as e:
            self.result.emit(False, f"Worker error: {e}", None)
        finally:
            self.finished.emit()


# --- Parameter Dialog ---
class ParameterDialog(QDialog):
    def __init__(self, plugin_name, expected_args, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Parameters for {plugin_name}")
        self.setMinimumWidth(400)
        self.layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()
        self.inputs_widgets = {}  # Stores the actual QLineEdit, QSpinBox etc.
        self.arg_definitions = expected_args  # Store for later retrieval of names

        for arg_def in expected_args:
            arg_name = arg_def.get('name', f"arg_{len(self.inputs_widgets)}")
            arg_type = arg_def.get('type', 'str').lower()
            description = arg_def.get('description', 'N/A')
            default_value = arg_def.get('default')  # Default can be None
            required = arg_def.get('required', False)  # Assume not required if not specified

            label_text = f"{arg_name}"
            if required:
                label_text += "*"
            label_text += f" ({description}):"
            label = QLabel(label_text)

            widget = None
            if arg_type == 'int':
                widget = QSpinBox(self)
                widget.setRange(-2147483648, 2147483647)  # Standard int range
                if default_value is not None:
                    try:
                        widget.setValue(int(default_value))
                    except ValueError:
                        pass
            elif arg_type == 'file':  # Special type for file paths
                widget_layout = QHBoxLayout()
                line_edit = QLineEdit(self)
                if default_value is not None: line_edit.setText(str(default_value))
                browse_button = QPushButton("Browse...", self)
                # Use a lambda to pass the line_edit to the browse function
                browse_button.clicked.connect(lambda _, le=line_edit: self.browse_file(le))
                widget_layout.addWidget(line_edit)
                widget_layout.addWidget(browse_button)
                widget = QWidget()  # Use a container widget for the QHBoxLayout
                widget.setLayout(widget_layout)
                self.inputs_widgets[arg_name] = line_edit  # Store the line_edit for value retrieval
            else:  # Default to string
                widget = QLineEdit(self)
                if default_value is not None: widget.setText(str(default_value))

            if arg_type != 'file':  # For file, we stored line_edit directly
                self.inputs_widgets[arg_name] = widget

            self.form_layout.addRow(label, widget)

        self.layout.addLayout(self.form_layout)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def browse_file(self, line_edit_widget):
        # For 'save' type args, use QFileDialog.getSaveFileName
        # For 'open' type args, use QFileDialog.getOpenFileName
        # Assuming 'open' for now
        filePath, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*)")
        if filePath:
            line_edit_widget.setText(filePath)

        # In main_app.py, inside ParameterDialog class

    def get_parameters_as_list(self):
        params_list = []
        # Iterate based on the original order of expected_args to maintain positional correspondence if needed
        for arg_def in self.arg_definitions:
            arg_name = arg_def.get('name')
            widget = self.inputs_widgets.get(arg_name)  # This gets QLineEdit, QSpinBox, etc.
            value_str = None  # We'll store the string representation of the value here
            is_boolean_flag = arg_def.get('type',
                                          'str').lower() == 'bool_flag'  # A new type for checkbox-like flags
            required = arg_def.get('required', False)

            if is_boolean_flag:
                # Assuming widget here would be a QCheckBox if fully implemented
                # For now, let's simulate. If ParameterDialog had a QCheckBox for this arg_name:
                # if widget.isChecked():
                #    params_list.append(f"--{arg_name.lstrip('-')}")
                # For this example, we'll assume bool_flag args are not 'required' in the sense of needing a value.
                # They are either present (flag passed) or absent.
                # The ParameterDialog would need a QCheckBox for this.
                # Since we don't have a QCheckBox yet in ParameterDialog for a 'bool_flag' type,
                # this path won't be fully active unless you add one.
                # Let's assume for now that if a bool_flag is defined but not 'required' to be true,
                # we don't add it unless the (future) checkbox is checked.
                # If you want to pass it if a default is true, that's another logic layer.
                # For now, we'll just skip adding it if it's a bool_flag and we don't have a UI element.
                pass  # Placeholder: Add logic if QCheckBox is implemented for 'bool_flag'

            elif isinstance(widget, QLineEdit):
                value_str = widget.text()
            elif isinstance(widget, QSpinBox):
                value_str = str(widget.value())

            # Check required for non-boolean flags (boolean flags are either present or not)
            if not is_boolean_flag and required and (value_str is None or value_str.strip() == ""):
                QMessageBox.warning(self, "Missing Parameter", f"Required parameter '{arg_name}' is not provided.")
                return None  # Indicate error

            # Construct the argument list
            # Ensure arg_name is valid before proceeding
            if not arg_name:
                print(f"Warning: Argument definition found without a name: {arg_def}")
                continue

            # For plugins that use argparse, it's better to pass as ['--arg-name', 'value']
            # If an arg name starts with '--' or '-', assume it's an option.
            if arg_name.startswith('-'):  # Explicitly an option like --my-option
                params_list.append(arg_name)
                if not is_boolean_flag:  # Boolean flags (like --verbose) don't take a value after them
                    params_list.append(value_str if value_str is not None else "")
            else:  # Positional, or needs to be converted to an option like --name value
                # Let's always convert to an option for argparse friendliness unless it's a bool_flag
                if is_boolean_flag:
                    # This would be where a QCheckBox's state determines if the flag is added
                    # Example: if self.inputs_widgets[arg_name].isChecked(): # Assuming inputs_widgets stores QCheckBox
                    # params_list.append(f"--{arg_name.lstrip('-')}")
                    # For now, we are not adding QCheckBox, so this part is illustrative.
                    # If you add a 'bool_flag' type to `expected_args` and a QCheckBox in the dialog,
                    # you'd check its state here.
                    # Let's say if `value_str` (from a hypothetical checkbox that sets 'true'/'false') is 'true':
                    if str(arg_def.get('default_bool_state',
                                       False)).lower() == 'true':  # Example: if default is true
                        pass  # This logic needs a UI element for bool_flag
                        # params_list.append(f"--{arg_name.lstrip('-')}")


                elif value_str is not None:  # Only add if there's a value (or it's required then checked above)
                    # Ensure it's an option like --input-file, even if arg_name was "input-file"
                    option_name = arg_name.lstrip('-')  # Remove leading dashes if any
                    if not option_name.startswith('-') and len(
                            option_name) > 1:  # for single letter options like -v, don't add --
                        params_list.append(f"--{option_name}")
                    elif not option_name.startswith('-') and len(option_name) == 1:
                        params_list.append(f"-{option_name}")
                    else:  # It already was --option or -o
                        params_list.append(arg_name)

                    params_list.append(value_str)
                # If value_str is None (e.g. optional field left blank) and not a bool_flag, we don't append anything for it.
                # Argparse handles optional arguments not being present.

        return params_list


class PluginMarketWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plugin Market (PyQt 5.10.1)")
        self.setGeometry(100, 100, 900, 700)

        self.cloud_connector = MockCloudConnector()
        self.plugin_manager = PluginManager(self.cloud_connector, local_plugins_dir="plugins")

        self.current_selected_plugin_id = None
        self.active_worker_thread = None
        self.active_worker_object = None

        self.init_ui()
        self.refresh_plugin_list()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        top_bar_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh List from Cloud")
        self.refresh_button.clicked.connect(self.refresh_plugin_list)
        top_bar_layout.addWidget(self.refresh_button)
        top_bar_layout.addStretch(1)
        main_layout.addLayout(top_bar_layout)

        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Available Plugins:"))
        self.plugin_list_widget = QListWidget()
        self.plugin_list_widget.currentItemChanged.connect(self.on_plugin_selected)
        left_layout.addWidget(self.plugin_list_widget)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.details_group = QGroupBox("Plugin Details")
        details_form_layout = QFormLayout()
        self.name_label = QLabel("N/A")
        self.desc_label = QLabel("N/A")
        self.desc_label.setWordWrap(True)
        self.version_label = QLabel("N/A")
        self.author_label = QLabel("N/A")
        self.status_label = QLabel("N/A")
        self.args_def_label = QLabel("N/A")  # To show argument definitions
        self.args_def_label.setWordWrap(True)

        details_form_layout.addRow("Name:", self.name_label)
        details_form_layout.addRow("Description:", self.desc_label)
        details_form_layout.addRow("Version:", self.version_label)
        details_form_layout.addRow("Author:", self.author_label)
        details_form_layout.addRow("Status:", self.status_label)
        details_form_layout.addRow("Expected Args:", self.args_def_label)  # Display args info
        self.details_group.setLayout(details_form_layout)
        right_layout.addWidget(self.details_group)

        action_layout = QHBoxLayout()
        self.download_button = QPushButton("Download")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download_selected_plugin)
        action_layout.addWidget(self.download_button)

        self.run_button = QPushButton("Run")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.run_selected_plugin)
        action_layout.addWidget(self.run_button)
        right_layout.addLayout(action_layout)

        right_layout.addWidget(QLabel("Plugin Output:"))
        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setFont(QFont("Courier New", 9))
        right_layout.addWidget(self.output_console)

        splitter.addWidget(right_widget)
        splitter.setSizes([300, 600])

        main_layout.addWidget(splitter)
        self.statusBar().showMessage("Ready.")

    def update_plugin_display_list(self):
        self.plugin_list_widget.clear()
        plugins = sorted(self.plugin_manager.available_plugins.values(), key=lambda p: p.name)
        for plugin in plugins:
            item_text = f"{plugin.name} (v{plugin.version})"
            if plugin.is_downloaded:
                item_text += " [Downloaded]"

            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.UserRole, plugin.id)
            self.plugin_list_widget.addItem(list_item)

        if self.current_selected_plugin_id:
            for i in range(self.plugin_list_widget.count()):
                item = self.plugin_list_widget.item(i)
                if item.data(Qt.UserRole) == self.current_selected_plugin_id:
                    self.plugin_list_widget.setCurrentItem(item)
                    break
        elif self.plugin_list_widget.count() > 0:
            self.plugin_list_widget.setCurrentRow(0)

        self.on_plugin_selected(self.plugin_list_widget.currentItem(), None)

    def refresh_plugin_list(self):
        self.statusBar().showMessage("Refreshing plugin list from cloud...")
        self.refresh_button.setEnabled(False)
        self.plugin_manager.discover_plugins()  # This now also updates expected_args
        self.update_plugin_display_list()
        self.statusBar().showMessage("Plugin list refreshed.", 3000)
        self.refresh_button.setEnabled(True)

    def on_plugin_selected(self, current_item, previous_item):
        if not current_item:
            self.current_selected_plugin_id = None
            self.name_label.setText("N/A")
            self.desc_label.setText("N/A")
            self.version_label.setText("N/A")
            self.author_label.setText("N/A")
            self.status_label.setText("N/A")
            self.args_def_label.setText("N/A")
            self.download_button.setEnabled(False)
            self.run_button.setEnabled(False)
            return

        plugin_id = current_item.data(Qt.UserRole)
        self.current_selected_plugin_id = plugin_id
        plugin = self.plugin_manager.get_plugin_by_id(plugin_id)

        if plugin:
            self.name_label.setText(plugin.name)
            self.desc_label.setText(plugin.description)
            self.version_label.setText(plugin.version)
            self.author_label.setText(plugin.author)
            self.status_label.setText(plugin.status_message)

            args_text = "None"
            if plugin.expected_args:
                args_text = "\n".join([
                    f"- {arg.get('name')}{'*' if arg.get('required') else ''} ({arg.get('type', 'str')}): {arg.get('description', 'N/A')}"
                    for arg in plugin.expected_args
                ])
            self.args_def_label.setText(args_text)

            task_is_active = self.active_worker_thread is not None and self.active_worker_thread.isRunning()

            self.download_button.setEnabled(not plugin.is_downloaded and not task_is_active)
            self.run_button.setEnabled(
                plugin.is_downloaded and \
                (plugin.local_path and os.path.exists(plugin.local_path)) and \
                not task_is_active
            )
        else:
            self.current_selected_plugin_id = None
            QMessageBox.warning(self, "Error", f"Could not find details for plugin ID: {plugin_id}")

    def _start_worker_task(self, task_callable, *args, **kwargs):
        if self.active_worker_thread and self.active_worker_thread.isRunning():
            QMessageBox.information(self, "Busy", "Another operation is already in progress.")
            return None

        worker = Worker(task_callable, *args, **kwargs)
        thread = QThread()
        self.active_worker_object = worker
        self.active_worker_thread = thread
        worker.moveToThread(thread)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_active_worker_references)
        thread.started.connect(worker.run)
        thread.start()
        return worker

    def _clear_active_worker_references(self):
        self.active_worker_object = None
        self.active_worker_thread = None
        current_list_item = self.plugin_list_widget.currentItem()
        self.on_plugin_selected(current_list_item, None)

    def _task_wrapper_for_download(self, plugin_id):
        plugin = self.plugin_manager.get_plugin_by_id(plugin_id)
        if not plugin: return False, "Plugin not found", None
        success, msg = self.plugin_manager.download_plugin(plugin_id)
        return success, msg, plugin

    def download_selected_plugin(self):
        if not self.current_selected_plugin_id: return
        plugin = self.plugin_manager.get_plugin_by_id(self.current_selected_plugin_id)
        if not plugin: return

        self.statusBar().showMessage(f"Downloading {plugin.name}...")
        self.download_button.setEnabled(False)
        self.run_button.setEnabled(False)

        worker_obj = self._start_worker_task(self._task_wrapper_for_download, self.current_selected_plugin_id)
        if worker_obj:
            worker_obj.result.connect(self.handle_download_result)
        else:
            self.statusBar().showMessage(f"Could not start download for {plugin.name}. Another task might be active.",
                                         3000)
            self.on_plugin_selected(self.plugin_list_widget.currentItem(), None)

    def handle_download_result(self, success, message, plugin_obj):  # plugin_obj is Plugin instance
        if plugin_obj:
            self.statusBar().showMessage(f"Download of {plugin_obj.name}: {message}", 5000)
        else:
            self.statusBar().showMessage(f"Download operation: {message}", 5000)

        self.update_plugin_display_list()
        current_list_item = self.plugin_list_widget.currentItem()
        if current_list_item and plugin_obj and current_list_item.data(Qt.UserRole) == plugin_obj.id:
            self.on_plugin_selected(current_list_item, None)  # Re-select to update details pane if needed

    def _task_wrapper_for_run(self, plugin_id, plugin_args_list=None):  # Added plugin_args_list
        plugin = self.plugin_manager.get_plugin_by_id(plugin_id)
        if not plugin: return False, "Plugin not found", None

        def emit_output_from_worker_context(text):
            if self.active_worker_object:
                self.active_worker_object.progress.emit(text)

        success, msg = self.plugin_manager.run_plugin(plugin_id,
                                                      output_callback=emit_output_from_worker_context,
                                                      args_for_plugin=plugin_args_list if plugin_args_list else [])  # Pass args
        return success, msg, plugin

    def run_selected_plugin(self):
        if not self.current_selected_plugin_id:
            return

        plugin = self.plugin_manager.get_plugin_by_id(self.current_selected_plugin_id)
        if not plugin: return

        plugin_args_to_pass = []  # This will hold the ['--arg', 'value', '--another', 'val'] list
        if plugin.expected_args:
            dialog = ParameterDialog(plugin.name, plugin.expected_args, self)
            if dialog.exec_() == QDialog.Accepted:
                plugin_args_to_pass = dialog.get_parameters_as_list()
                if plugin_args_to_pass is None:  # An error occurred (e.g. missing required param)
                    self.statusBar().showMessage("Parameter validation failed.", 3000)
                    return  # Stop execution
            else:
                self.statusBar().showMessage(f"Run cancelled for {plugin.name}.", 3000)
                return  # User cancelled

        self.output_console.clear()
        self.append_to_output_console(f"Attempting to run '{plugin.name}' with args: {plugin_args_to_pass}...")
        self.statusBar().showMessage(f"Running {plugin.name}...")
        self.run_button.setEnabled(False)
        self.download_button.setEnabled(False)

        # Pass plugin_args_to_pass to the worker task
        worker_obj = self._start_worker_task(self._task_wrapper_for_run, self.current_selected_plugin_id,
                                             plugin_args_to_pass)
        if worker_obj:
            worker_obj.progress.connect(self.append_to_output_console)
            worker_obj.result.connect(self.handle_run_result)
        else:
            self.statusBar().showMessage(f"Could not start run for {plugin.name}. Another task might be active.", 3000)
            self.append_to_output_console("Failed to start run task.")
            self.on_plugin_selected(self.plugin_list_widget.currentItem(), None)

    def handle_run_result(self, success, message, plugin_obj):  # plugin_obj is Plugin instance
        final_message = message if message else ("Success" if success else "Failed without specific message")
        if plugin_obj:
            self.statusBar().showMessage(f"Run of {plugin_obj.name}: {plugin_obj.status_message}", 5000)
            self.append_to_output_console(f"--- {plugin_obj.name} execution finished ---")
            self.append_to_output_console(f"Result: {plugin_obj.status_message}")  # Use status from plugin manager
            if "failed with code" in final_message.lower() or "error output" in final_message.lower():
                if not any(line.strip().endswith(final_message.strip()) for line in
                           self.output_console.toPlainText().splitlines()):
                    self.append_to_output_console(f"Details: {final_message}")
        else:
            self.statusBar().showMessage(f"Run operation: {final_message}", 5000)
            self.append_to_output_console(f"Run operation: {final_message}")

        self.update_plugin_display_list()
        current_list_item = self.plugin_list_widget.currentItem()
        if current_list_item and plugin_obj and current_list_item.data(Qt.UserRole) == plugin_obj.id:
            self.on_plugin_selected(current_list_item, None)  # Re-select to update details and button states

    def append_to_output_console(self, text):
        self.output_console.append(text.rstrip('\n'))
        self.output_console.ensureCursorVisible()

    def closeEvent(self, event):
        if self.active_worker_thread and self.active_worker_thread.isRunning():
            reply = QMessageBox.question(self, 'Confirm Exit',
                                         "A task is currently running. Are you sure you want to exit?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.active_worker_thread.quit()
                if not self.active_worker_thread.wait(1000):  # Shorter wait
                    print("Worker thread did not finish gracefully on close.")
                event.accept()
            else:
                event.ignore()
                return
        else:
            event.accept()

        if event.isAccepted():
            self.plugin_manager._save_local_plugin_db()


if __name__ == '__main__':
    # Create directories if they don't exist
    for dir_path in ["plugins", "sample_plugins_for_cloud"]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"Created directory: {dir_path}")

    app = QApplication(sys.argv)
    market_window = PluginMarketWindow()
    market_window.show()
    sys.exit(app.exec_())