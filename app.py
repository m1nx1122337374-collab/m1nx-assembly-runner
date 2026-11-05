import os
import sys
import zipfile
import subprocess
from flask import Flask, request, render_template_string, Response, stream_with_context

app = Flask(__name__)
UPLOAD_FOLDER = './uploaded_project'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# গ্লোবাল প্রসেস ভ্যারিয়েবল যাতে প্রক্সি ব্যাকগ্রাউন্ডে চলতে থাকে
proxy_process = None

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>M1NX Auto Cloud Runner</title>
    <style>
        body { background-color: #0d1117; color: #58a6ff; font-family: 'Courier New', Courier, monospace; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: #161b22; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); border: 1px solid #30363d; }
        h2 { color: #00ff66; text-align: center; margin-bottom: 20px; font-weight: bold; }
        .upload-box { border: 2px dashed #30363d; border-radius: 8px; padding: 30px; text-align: center; background: #0d1117; margin-bottom: 20px; }
        input[type="file"] { display: none; }
        label { background: #238636; color: #ffffff; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-weight: bold; display: inline-block; }
        label:hover { background: #2ea043; }
        button { background: #1f6feb; color: white; border: none; padding: 12px 30px; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; margin-top: 15px; }
        button:hover { background: #388bfd; }
        #terminal { background: #050505; color: #00ff66; border: 1px solid #30363d; padding: 15px; height: 350px; overflow-y: auto; border-radius: 6px; margin-top: 20px; font-size: 14px; white-space: pre-wrap; word-break: break-all; }
        .success-box { background: #238636; color: white; padding: 15px; border-radius: 6px; text-align: center; font-weight: bold; margin-top: 15px; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>⚡ M1NX ZIP CLOUD DEPLOYER ⚡</h2>
        <form id="uploadForm" action="/deploy" method="post" enctype="multipart/form-data">
            <div class="upload-box">
                <p style="color:#8b949e;">আপনার প্রজেক্টের ZIP ফাইলটি সিলেক্ট করুন</p>
                <label for="zipFile">Select ZIP File</label>
                <input type="file" name="zip_file" id="zipFile" accept=".zip" required onchange="updateFileName()">
                <p id="fileName" style="color:#58a6ff; margin-top: 10px;"></p>
            </div>
            <button type="submit">Start Deployment & Run Proxy</button>
        </form>

        <div id="terminal">[TERMUX LOG] আপলোডের জন্য রেডি...\n</div>
        <div id="successBox" class="success-box">
            🚀 প্রক্সি সার্ভার সফলভাবে ব্যাকগ্রাউন্ডে রান করছে!<br>
            <span id="proxyInfo" style="font-size: 13px; color: #d2a8ff;"></span>
        </div>
    </div>

    <script>
        function updateFileName() {
            const input = document.getElementById('zipFile');
            document.getElementById('fileName').innerText = "Selected: " + input.files[0].name;
        }

        const form = document.getElementById('uploadForm');
        form.onsubmit = async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const term = document.getElementById('terminal');
            const successBox = document.getElementById('successBox');
            term.innerHTML = "[TERMUX LOG] জিপ ফাইল আপলোড ও এক্সট্র্যাক্ট হচ্ছে...\n";
            successBox.style.display = "none";

            const response = await fetch('/deploy', { method: 'POST', body: formData });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const text = decoder.decode(value);
                term.innerHTML += text;
                term.scrollTop = term.scrollHeight;

                if (text.includes("PROXY_STARTED_SUCCESS")) {
                    successBox.style.display = "block";
                    document.getElementById('proxyInfo').innerText = "Target Port: 7777 (Free Fire CDN Interceptor Active)";
                }
            }
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_LAYOUT)

@app.route('/deploy', methods=['POST'])
def deploy():
    def generate_logs():
        global proxy_process
        if 'zip_file' not in request.files:
            yield "[ERROR] কোনো জিপ ফাইল পাওয়া যায়নি!\n"
            return
        
        file = request.files['zip_file']
        if file.filename == '':
            yield "[ERROR] ফাইল নির্বাচন করা হয়নি!\n"
            return

        zip_path = os.path.join('/tmp', 'project.zip')
        file.save(zip_path)
        yield "[INFO] ZIP ফাইল সফলভাবে সার্ভারে রিসিভ করা হয়েছে।\n"
        yield "[INFO] ফাইল এক্সট্রাক্ট করা হচ্ছে...\n"

        extract_dir = app.config['UPLOAD_FOLDER']
        if not os.path.exists(extract_dir):
            os.makedirs(extract_dir)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        yield "[SUCCESS] ফাইল সফলভাবে আনজিপ করা শেষ!\n"

        # Dependencies check
        req_file = os.path.join(extract_dir, 'requirements.txt')
        if os.path.exists(req_file):
            yield "[TERMUX LOG] pip install -r requirements.txt রান করা হচ্ছে...\n"
            pip_proc = subprocess.Popen([sys.executable, "-m", "pip", "install", "-r", req_file], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(pip_proc.stdout.readline, ''):
                yield line
            pip_proc.stdout.close()
            pip_proc.wait()

        # Run proxy script (run.py)
        run_script = os.path.join(extract_dir, 'run.py')
        if os.path.exists(run_script):
            yield f"[TERMUX LOG] python run.py ব্যাকগ্রাউন্ডে চালু করা হচ্ছে...\n"
            
            # Stop previous proxy instance if running
            if proxy_process:
                proxy_process.terminate()

            # Start run.py as background process inside the extracted folder
            proxy_process = subprocess.Popen(
                [sys.executable, run_script],
                cwd=extract_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            yield "[SUCCESS] run.py প্রসেস সফলভাবে স্পন করা হয়েছে!\n"
            yield "PROXY_STARTED_SUCCESS\n"
        else:
            yield "[ERROR] প্রজেক্ট ফোল্ডারে run.py ফাইলটি পাওয়া যায়নি!\n"

    return Response(stream_with_context(generate_logs()), mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
