"""
Safe launcher for the Flask application with timeout protection
"""
import os
import sys
import subprocess
import time
import signal
import psutil
import threading

def is_windows():
    return sys.platform.startswith('win')

def kill_process_tree(pid):
    """Kill a process and all its children"""
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except:
                pass
        parent.kill()
    except:
        pass

def timeout_handler(process):
    """Kill the process after timeout"""
    print("\n\n*** TIMEOUT: Application startup took too long! ***")
    print("There may be an infinite loop or hanging connection during initialization.")
    print("Terminating process...")
    
    if process.poll() is None:  # Process is still running
        if is_windows():
            try:
                kill_process_tree(process.pid)
            except:
                os.system(f"taskkill /F /PID {process.pid} /T")
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except:
                os.kill(process.pid, signal.SIGTERM)

def main():
    print("Starting application with loop protection...")
    
    # Set environment variables to help prevent hangs
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # If using Google Cloud, set a shorter timeout
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        os.environ['HTTP_TIMEOUT'] = '10'
    
    # Create command
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, 'app.py')
    
    # Create command to run the Flask app
    cmd = [sys.executable, app_path]
    
    # Set process group
    kwargs = {}
    if not is_windows():
        kwargs['preexec_fn'] = os.setsid
    
    # Start Flask application
    print(f"Launching: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
        **kwargs
    )
    
    # Set a timeout (30 seconds)
    timeout = 30  # seconds
    timer = threading.Timer(timeout, timeout_handler, args=[process])
    timer.start()
    
    # Track if we've seen the "Running on" message
    startup_complete = False
    line_count = 0
    
    try:
        # Monitor output
        for line in process.stdout:
            line_count += 1
            print(line.rstrip())
            
            # Look for the line that indicates Flask is running
            if "Running on" in line:
                startup_complete = True
                print("\n*** Application started successfully! ***\n")
                # Cancel the timeout since startup is complete
                timer.cancel()
            
            # If we've seen too many lines without startup completing, it might be in a loop
            if line_count > 200 and not startup_complete:
                print("\n\n*** WARNING: Excessive output without completing startup! ***")
                print("This may indicate a loop. Consider checking your code for infinite loops.")
                # We don't terminate here, but warn the user
    except KeyboardInterrupt:
        print("\nUser interrupted. Shutting down...")
        if timer.is_alive():
            timer.cancel()
        if process.poll() is None:  # Process is still running
            if is_windows():
                try:
                    kill_process_tree(process.pid)
                except:
                    os.system(f"taskkill /F /PID {process.pid} /T")
            else:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except:
                    os.kill(process.pid, signal.SIGTERM)
    finally:
        # Always cancel the timer if it's still running
        if timer.is_alive():
            timer.cancel()
        
        # Wait for process to finish
        exit_code = process.wait()
        print(f"Process exited with code {exit_code}")
        return exit_code

if __name__ == "__main__":
    main()