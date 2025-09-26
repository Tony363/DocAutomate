#!/usr/bin/env python3
"""
DocAutomate Desktop GUI Client
Single-file tkinter application with direct ClaudeCLI integration
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import queue
import httpx
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import asyncio
from typing import Optional, Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_cli import ClaudeCLI, SuperClaudeMode


class DocAutomateGUI:
    """Main GUI Application for DocAutomate"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("DocAutomate Desktop Client")
        self.root.geometry("1400x800")
        
        # Initialize Claude CLI directly
        self.claude = ClaudeCLI()
        
        # Queue for thread communication
        self.queue = queue.Queue()
        
        # API configuration
        self.api_base = "http://localhost:8000"
        self.api_port = int(os.getenv("API_PORT", "8000"))
        self.api_base = f"http://localhost:{self.api_port}"
        
        # State tracking
        self.current_document_id = None
        self.workflows = []
        self.documents = {}
        self.command_history = []
        self.history_index = -1
        
        # Setup UI
        self.setup_styles()
        self.setup_ui()
        self.setup_menu()
        self.bind_shortcuts()
        
        # Start background tasks
        self.start_queue_processor()
        self.load_workflows()
        self.check_api_connection()
        
        # Welcome message
        self.append_claude_output("Welcome to DocAutomate Desktop Client!\n", "system")
        self.append_claude_output("Claude CLI is ready. Try '--brainstorm' or '--help'\n", "system")
        
    def setup_styles(self):
        """Configure ttk styles for modern look"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        self.colors = {
            'bg': '#f0f0f0',
            'fg': '#333333',
            'select': '#0078d4',
            'button': '#0078d4',
            'success': '#107c10',
            'error': '#d13438',
            'warning': '#ca5010',
            'info': '#0078d4'
        }
        
        # Configure button styles
        style.configure('Action.TButton', foreground='white')
        style.map('Action.TButton',
                 background=[('active', '#106ebe'), ('!active', self.colors['button'])])
    
    def setup_ui(self):
        """Create the main UI layout"""
        # Create main container
        main_container = ttk.Frame(self.root, padding="5")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_container.columnconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=2)
        main_container.rowconfigure(0, weight=1)
        
        # Create left panel (Document Operations)
        self.create_left_panel(main_container)
        
        # Create separator
        separator = ttk.Separator(main_container, orient='vertical')
        separator.grid(row=0, column=1, sticky=(tk.N, tk.S), padx=5)
        
        # Create right panel (Claude Chat)
        self.create_right_panel(main_container)
        
        # Create status bar
        self.create_status_bar()
        
    def create_left_panel(self, parent):
        """Create document operations panel"""
        left_frame = ttk.LabelFrame(parent, text="Document Operations", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Upload section
        upload_frame = ttk.Frame(left_frame)
        upload_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.upload_btn = ttk.Button(
            upload_frame, 
            text="📁 Upload Document",
            command=self.upload_document,
            style='Action.TButton'
        )
        self.upload_btn.pack(fill=tk.X)
        
        # Workflow section
        workflow_frame = ttk.Frame(left_frame)
        workflow_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(workflow_frame, text="Workflow:").pack(anchor=tk.W)
        self.workflow_combo = ttk.Combobox(workflow_frame, state="readonly")
        self.workflow_combo.pack(fill=tk.X, pady=(5, 0))
        
        # Workflow parameters
        params_frame = ttk.LabelFrame(left_frame, text="Parameters", padding="5")
        params_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.params_text = tk.Text(params_frame, height=4, width=40)
        self.params_text.pack(fill=tk.BOTH)
        self.params_text.insert('1.0', '{\n  "auto_execute": true\n}')
        
        # Execute button
        self.execute_btn = ttk.Button(
            left_frame,
            text="▶ Execute Workflow",
            command=self.execute_workflow,
            style='Action.TButton'
        )
        self.execute_btn.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Documents list
        doc_frame = ttk.LabelFrame(left_frame, text="Documents", padding="5")
        doc_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        left_frame.rowconfigure(4, weight=1)
        
        # Create treeview for documents
        self.doc_tree = ttk.Treeview(doc_frame, columns=('Status', 'Type'), show='tree headings', height=10)
        self.doc_tree.heading('#0', text='Document')
        self.doc_tree.heading('Status', text='Status')
        self.doc_tree.heading('Type', text='Type')
        self.doc_tree.column('#0', width=200)
        self.doc_tree.column('Status', width=80)
        self.doc_tree.column('Type', width=80)
        
        # Add scrollbar
        doc_scroll = ttk.Scrollbar(doc_frame, orient='vertical', command=self.doc_tree.yview)
        self.doc_tree.configure(yscrollcommand=doc_scroll.set)
        
        self.doc_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        doc_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind document selection
        self.doc_tree.bind('<<TreeviewSelect>>', self.on_document_select)
        
        # Results area
        results_frame = ttk.LabelFrame(left_frame, text="Results", padding="5")
        results_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.results_text = scrolledtext.ScrolledText(results_frame, height=8, width=40, wrap=tk.WORD)
        self.results_text.pack(fill=tk.BOTH)
        
    def create_right_panel(self, parent):
        """Create Claude chat interface panel"""
        right_frame = ttk.LabelFrame(parent, text="Claude Assistant", padding="10")
        right_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        parent.columnconfigure(2, weight=2)
        
        # Chat display
        chat_frame = ttk.Frame(right_frame)
        chat_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)
        
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, 
            height=30, 
            width=80,
            wrap=tk.WORD,
            font=('Consolas', 10)
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for formatting
        self.chat_display.tag_config('user', foreground='#0078d4', font=('Consolas', 10, 'bold'))
        self.chat_display.tag_config('claude', foreground='#107c10')
        self.chat_display.tag_config('system', foreground='#666666', font=('Consolas', 9, 'italic'))
        self.chat_display.tag_config('error', foreground='#d13438')
        self.chat_display.tag_config('code', background='#f3f3f3', font=('Courier', 10))
        
        # Input section
        input_frame = ttk.Frame(right_frame)
        input_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Command input
        ttk.Label(input_frame, text="Command:").pack(anchor=tk.W)
        
        input_container = ttk.Frame(input_frame)
        input_container.pack(fill=tk.X, pady=(5, 0))
        
        self.command_input = tk.Entry(input_container, font=('Consolas', 10))
        self.command_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Bind Enter key and history navigation
        self.command_input.bind('<Return>', lambda e: self.send_to_claude())
        self.command_input.bind('<Up>', self.history_up)
        self.command_input.bind('<Down>', self.history_down)
        
        # Buttons
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(button_frame, text="Send", command=self.send_to_claude).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Clear", command=self.clear_chat).pack(side=tk.LEFT, padx=(0, 5))
        
        # Mode selection
        mode_frame = ttk.LabelFrame(right_frame, text="SuperClaude Modes", padding="5")
        mode_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        
        mode_container = ttk.Frame(mode_frame)
        mode_container.pack(fill=tk.X)
        
        # Create mode buttons
        modes = [
            ("Brainstorm", "--brainstorm"),
            ("Task Manage", "--task-manage"),
            ("Delegate", "--delegate"),
            ("Token Efficient", "--uc"),
            ("Loop", "--loop")
        ]
        
        for i, (label, flag) in enumerate(modes):
            btn = ttk.Button(
                mode_container,
                text=label,
                width=12,
                command=lambda f=flag: self.insert_mode(f)
            )
            btn.grid(row=0, column=i, padx=2)
    
    def create_status_bar(self):
        """Create status bar at bottom of window"""
        status_frame = ttk.Frame(self.root)
        status_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        self.status_label = ttk.Label(
            status_frame, 
            text="Ready | API: Checking...",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.progress = ttk.Progressbar(
            status_frame,
            mode='indeterminate',
            length=100
        )
        self.progress.pack(side=tk.RIGHT, padx=5)
        
    def setup_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Upload Document", command=self.upload_document, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Refresh Workflows", command=self.load_workflows)
        file_menu.add_command(label="Refresh Documents", command=self.load_documents)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit, accelerator="Ctrl+Q")
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Clear Chat", command=self.clear_chat, accelerator="Ctrl+L")
        edit_menu.add_command(label="Copy", command=self.copy_selection, accelerator="Ctrl+C")
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="API Status", command=self.check_api_connection)
        view_menu.add_command(label="Claude Status", command=self.check_claude_status)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="SuperClaude Help", command=lambda: self.send_command("--help"))
        
    def bind_shortcuts(self):
        """Bind keyboard shortcuts"""
        self.root.bind('<Control-o>', lambda e: self.upload_document())
        self.root.bind('<Control-q>', lambda e: self.root.quit())
        self.root.bind('<Control-l>', lambda e: self.clear_chat())
        
    def start_queue_processor(self):
        """Start processing queue messages from threads"""
        def process_queue():
            try:
                while True:
                    try:
                        msg_type, data = self.queue.get_nowait()
                        
                        if msg_type == 'claude_response':
                            self.append_claude_output(data, 'claude')
                        elif msg_type == 'claude_error':
                            self.append_claude_output(f"Error: {data}", 'error')
                        elif msg_type == 'api_response':
                            self.handle_api_response(data)
                        elif msg_type == 'status':
                            self.update_status(data)
                        elif msg_type == 'progress_start':
                            self.progress.start(10)
                        elif msg_type == 'progress_stop':
                            self.progress.stop()
                            
                    except queue.Empty:
                        break
            finally:
                # Schedule next check
                self.root.after(100, process_queue)
        
        # Start processing
        process_queue()
    
    def append_claude_output(self, text, tag='claude'):
        """Append text to chat display with formatting"""
        self.chat_display.insert(tk.END, text, tag)
        self.chat_display.see(tk.END)
        
    def send_to_claude(self):
        """Send command to Claude CLI"""
        command = self.command_input.get().strip()
        if not command:
            return
            
        # Add to history
        self.command_history.append(command)
        self.history_index = len(self.command_history)
        
        # Display user command
        self.append_claude_output(f"\nYou: {command}\n", 'user')
        
        # Clear input
        self.command_input.delete(0, tk.END)
        
        # Start progress
        self.queue.put(('progress_start', None))
        self.queue.put(('status', f"Sending to Claude: {command[:50]}..."))
        
        # Run in thread
        thread = threading.Thread(target=self._claude_worker, args=(command,))
        thread.daemon = True
        thread.start()
        
    def _claude_worker(self, command):
        """Worker thread for Claude CLI interaction"""
        try:
            # Parse for special modes
            mode = None
            if '--brainstorm' in command:
                mode = SuperClaudeMode.BRAINSTORM
            elif '--task-manage' in command:
                mode = SuperClaudeMode.TASK_MANAGE
            elif '--uc' in command:
                mode = SuperClaudeMode.TOKEN_EFFICIENT
                
            # Call Claude CLI directly
            if mode:
                result = self.claude.execute_with_mode(command, mode=mode)
            else:
                result = self.claude.chat(command)
                
            # Send response to UI
            self.queue.put(('claude_response', f"Claude: {result}\n"))
            self.queue.put(('status', "Ready"))
            
        except Exception as e:
            self.queue.put(('claude_error', str(e)))
            self.queue.put(('status', "Error occurred"))
        finally:
            self.queue.put(('progress_stop', None))
    
    def send_command(self, command):
        """Programmatically send a command"""
        self.command_input.delete(0, tk.END)
        self.command_input.insert(0, command)
        self.send_to_claude()
        
    def insert_mode(self, mode_flag):
        """Insert mode flag into command input"""
        current = self.command_input.get()
        self.command_input.delete(0, tk.END)
        self.command_input.insert(0, f"{mode_flag} {current}".strip())
        self.command_input.focus()
        
    def history_up(self, event):
        """Navigate command history up"""
        if self.command_history and self.history_index > 0:
            self.history_index -= 1
            self.command_input.delete(0, tk.END)
            self.command_input.insert(0, self.command_history[self.history_index])
            
    def history_down(self, event):
        """Navigate command history down"""
        if self.command_history and self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self.command_input.delete(0, tk.END)
            self.command_input.insert(0, self.command_history[self.history_index])
            
    def clear_chat(self):
        """Clear chat display"""
        self.chat_display.delete('1.0', tk.END)
        self.append_claude_output("Chat cleared.\n", 'system')
        
    def copy_selection(self):
        """Copy selected text to clipboard"""
        try:
            selection = self.chat_display.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selection)
        except tk.TclError:
            pass
    
    def upload_document(self):
        """Upload document to API"""
        file_path = filedialog.askopenfilename(
            title="Select Document",
            filetypes=[
                ("All Documents", "*.pdf;*.docx;*.txt;*.xlsx"),
                ("PDF Files", "*.pdf"),
                ("Word Documents", "*.docx"),
                ("Text Files", "*.txt"),
                ("Excel Files", "*.xlsx"),
                ("All Files", "*.*")
            ]
        )
        
        if not file_path:
            return
            
        # Start upload in thread
        self.queue.put(('progress_start', None))
        self.queue.put(('status', f"Uploading {Path(file_path).name}..."))
        
        thread = threading.Thread(target=self._upload_worker, args=(file_path,))
        thread.daemon = True
        thread.start()
        
    def _upload_worker(self, file_path):
        """Worker thread for document upload"""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (Path(file_path).name, f, 'application/octet-stream')}
                response = httpx.post(
                    f"{self.api_base}/documents/upload",
                    files=files,
                    timeout=30.0
                )
                
            if response.status_code == 200:
                data = response.json()
                self.queue.put(('api_response', {'type': 'upload', 'data': data}))
                self.queue.put(('status', f"Uploaded: {data.get('document_id', 'Unknown')}"))
            else:
                self.queue.put(('api_response', {'type': 'error', 'data': response.text}))
                self.queue.put(('status', "Upload failed"))
                
        except Exception as e:
            self.queue.put(('api_response', {'type': 'error', 'data': str(e)}))
            self.queue.put(('status', "Upload error"))
        finally:
            self.queue.put(('progress_stop', None))
            self.load_documents()
    
    def execute_workflow(self):
        """Execute selected workflow"""
        workflow = self.workflow_combo.get()
        if not workflow:
            messagebox.showwarning("No Workflow", "Please select a workflow")
            return
            
        if not self.current_document_id:
            messagebox.showwarning("No Document", "Please select a document")
            return
            
        # Get parameters
        try:
            params = json.loads(self.params_text.get('1.0', tk.END))
        except json.JSONDecodeError:
            messagebox.showerror("Invalid JSON", "Parameters must be valid JSON")
            return
            
        # Start execution in thread
        self.queue.put(('progress_start', None))
        self.queue.put(('status', f"Executing {workflow}..."))
        
        thread = threading.Thread(
            target=self._execute_workflow_worker,
            args=(workflow, self.current_document_id, params)
        )
        thread.daemon = True
        thread.start()
        
    def _execute_workflow_worker(self, workflow, doc_id, params):
        """Worker thread for workflow execution"""
        try:
            payload = {
                'document_id': doc_id,
                'workflow_name': workflow,
                'parameters': params,
                'auto_execute': params.get('auto_execute', True)
            }
            
            response = httpx.post(
                f"{self.api_base}/workflows/execute",
                json=payload,
                timeout=60.0
            )
            
            if response.status_code == 200:
                data = response.json()
                self.queue.put(('api_response', {'type': 'workflow', 'data': data}))
                self.queue.put(('status', f"Workflow completed: {data.get('run_id', 'Unknown')}"))
            else:
                self.queue.put(('api_response', {'type': 'error', 'data': response.text}))
                self.queue.put(('status', "Workflow failed"))
                
        except Exception as e:
            self.queue.put(('api_response', {'type': 'error', 'data': str(e)}))
            self.queue.put(('status', "Workflow error"))
        finally:
            self.queue.put(('progress_stop', None))
    
    def handle_api_response(self, response):
        """Handle API response in UI"""
        if response['type'] == 'upload':
            data = response['data']
            self.results_text.delete('1.0', tk.END)
            self.results_text.insert('1.0', f"Upload Success!\nDocument ID: {data.get('document_id')}\n")
            self.results_text.insert(tk.END, f"Status: {data.get('status')}\n")
            
            # Add to document tree
            doc_id = data.get('document_id', 'Unknown')
            filename = data.get('filename', 'Unknown')
            self.doc_tree.insert('', 'end', values=('Uploaded', 'New'), text=filename, tags=(doc_id,))
            
        elif response['type'] == 'workflow':
            data = response['data']
            self.results_text.delete('1.0', tk.END)
            self.results_text.insert('1.0', f"Workflow Executed!\n")
            self.results_text.insert(tk.END, json.dumps(data, indent=2))
            
        elif response['type'] == 'error':
            self.results_text.delete('1.0', tk.END)
            self.results_text.insert('1.0', f"Error:\n{response['data']}")
            
        elif response['type'] == 'documents':
            # Update document tree
            self.doc_tree.delete(*self.doc_tree.get_children())
            for doc in response['data']:
                self.doc_tree.insert('', 'end', 
                                    values=(doc.get('status', 'Unknown'), doc.get('type', 'Unknown')),
                                    text=doc.get('filename', 'Unknown'),
                                    tags=(doc.get('document_id'),))
    
    def on_document_select(self, event):
        """Handle document selection"""
        selection = self.doc_tree.selection()
        if selection:
            item = self.doc_tree.item(selection[0])
            if item['tags']:
                self.current_document_id = item['tags'][0]
                self.update_status(f"Selected: {self.current_document_id}")
    
    def load_workflows(self):
        """Load available workflows from API"""
        def worker():
            try:
                response = httpx.get(f"{self.api_base}/workflows")
                if response.status_code == 200:
                    workflows = response.json()
                    self.workflows = [w['name'] for w in workflows.get('workflows', [])]
                    self.workflow_combo['values'] = self.workflows
                    if self.workflows:
                        self.workflow_combo.current(0)
                    self.queue.put(('status', f"Loaded {len(self.workflows)} workflows"))
            except Exception as e:
                self.queue.put(('status', f"Failed to load workflows: {e}"))
        
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
    
    def load_documents(self):
        """Load documents from API"""
        def worker():
            try:
                response = httpx.get(f"{self.api_base}/documents")
                if response.status_code == 200:
                    documents = response.json()
                    self.queue.put(('api_response', {'type': 'documents', 'data': documents}))
            except Exception:
                pass  # Silent fail for background refresh
        
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
    
    def check_api_connection(self):
        """Check API server connection"""
        def worker():
            try:
                response = httpx.get(f"{self.api_base}/health", timeout=2.0)
                if response.status_code == 200:
                    self.queue.put(('status', f"API: Connected to {self.api_base}"))
                else:
                    self.queue.put(('status', f"API: Server error ({response.status_code})"))
            except Exception:
                self.queue.put(('status', f"API: Not connected (is server running?)"))
        
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
    
    def check_claude_status(self):
        """Check Claude CLI status"""
        if self.claude.check_claude():
            messagebox.showinfo("Claude Status", "Claude CLI is installed and working!")
        else:
            messagebox.showwarning("Claude Status", "Claude CLI not found or not working")
    
    def update_status(self, message):
        """Update status bar"""
        current = self.status_label['text'].split(' | ')
        if len(current) > 1:
            self.status_label['text'] = f"{message} | {current[1]}"
        else:
            self.status_label['text'] = message
    
    def show_about(self):
        """Show about dialog"""
        about_text = """DocAutomate Desktop Client
Version 1.0.0

A native desktop interface for DocAutomate
with integrated Claude CLI assistant.

Features:
• Document upload and management
• Workflow execution
• Direct Claude CLI integration
• SuperClaude modes support

Built with Python and tkinter"""
        
        messagebox.showinfo("About DocAutomate", about_text)


def main():
    """Main entry point"""
    root = tk.Tk()
    
    # Set icon if available
    try:
        icon_path = Path(__file__).parent / 'icon.ico'
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
    except:
        pass
    
    # Create application
    app = DocAutomateGUI(root)
    
    # Start main loop
    root.mainloop()


if __name__ == "__main__":
    main()