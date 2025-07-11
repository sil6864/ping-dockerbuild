import subprocess
import json
import sys
import os
import time

def run_ping(target_ip, count, interval):
    try:
        result = subprocess.run(
            ['ping', '-c', str(count), '-i', str(interval), target_ip],
            capture_output=True,
            text=True,
            timeout=count * float(interval) * 2 + 10
        )
        return result.stdout, result.returncode
    except FileNotFoundError:
        print(f"Error: 'ping' command not found.", file=sys.stderr)
        return "", -1
    except subprocess.TimeoutExpired:
        print(f"Error: Ping command timed out.", file=sys.stderr)
        return "", -2
    except Exception as e:
        print(f"Unknown error during ping execution: {e}", file=sys.stderr)
        return "", -3

def analyze_with_openai(ping_output, api_url, api_key, model):
    messages = [
        {"role": "system", "content": "你是一个网络分析助手。请分析以下 Ping 测试结果，用简洁的中文总结网络状况，例如丢包率、延迟等，并给出可能的建议。"},
        {"role": "user", "content": f"请分析以下 Ping 结果：\n\n{ping_output}"}
    ]
    openai_payload = {
        "model": model,
        "messages": messages
    }
    json_payload_str = json.dumps(openai_payload)
    curl_command = [
        'curl', '-s', '-X', 'POST',
        '-H', 'Content-Type: application/json',
        '-H', f'Authorization: Bearer {api_key}',
        '-d', '@-',
        api_url
    ]
    try:
        result = subprocess.run(
            curl_command,
            input=json_payload_str,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            print(f"Error: AI API curl command failed, exit code: {result.returncode}", file=sys.stderr)
            print(f"Curl error output: {result.stderr}", file=sys.stderr)
            return None
        try:
            api_response = json.loads(result.stdout)
            analysis_text = api_response['choices'][0]['message']['content']
            return analysis_text
        except json.JSONDecodeError:
            print(f"Error: Cannot parse AI API JSON response. Raw output:\n{result.stdout}", file=sys.stderr)
            return None
        except (KeyError, IndexError):
            print(f"Error: AI API response structure abnormal. Raw response:\n{result.stdout}", file=sys.stderr)
            return None
    except FileNotFoundError:
        print(f"Error: 'curl' command not found.", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"Error: AI API call timed out.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Unknown error calling AI API: {e}", file=sys.stderr)
        return None

def send_telegram_message(chat_id, text, webhook_url):
    telegram_payload = {
        "chat_id": chat_id,
        "text": text
    }
    json_payload_str = json.dumps(telegram_payload)
    curl_command = [
        'curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
        '-X', 'POST',
        '-H', 'Content-Type: application/json',
        '-d', '@-',
        webhook_url
    ]
    try:
        result = subprocess.run(
            curl_command,
            input=json_payload_str,
            capture_output=True,
            text=True,
            timeout=30
        )
        http_status = result.stdout.strip()
        if result.returncode != 0:
            print(f"Error: Telegram Webhook curl command failed, exit code: {result.returncode}", file=sys.stderr)
            print(f"Curl error output: {result.stderr}", file=sys.stderr)
            return False
        if http_status == "200":
            return True
        else:
            print(f"Error: Telegram Webhook returned non-200 status code: {http_status}", file=sys.stderr)
            return False
    except FileNotFoundError:
        print(f"Error: 'curl' command not found.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"Error: Sending Telegram message timed out.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Unknown error sending Telegram message: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    TARGET_IP = os.environ.get("TARGET_IP")
    PING_COUNT = int(os.environ.get("PING_COUNT", 60))
    PING_INTERVAL = float(os.environ.get("PING_INTERVAL", 1.0))
    OPENAI_API_URL = os.environ.get("OPENAI_API_URL")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "yuewen")
    TELEGRAM_WEBHOOK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

    required_vars = {
        "TARGET_IP": TARGET_IP,
        "OPENAI_API_URL": OPENAI_API_URL,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "TELEGRAM_WEBHOOK_URL": TELEGRAM_WEBHOOK_URL,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID
    }

    missing_vars = [var_name for var_name, value in required_vars.items() if value is None]

    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}", file=sys.stderr)
        sys.exit(1)

    ping_output, ping_status = run_ping(TARGET_IP, PING_COUNT, PING_INTERVAL)

    if ping_status != 0:
        error_message = f"Ping to {TARGET_IP} failed or timed out (status code: {ping_status}). Raw output:\n{ping_output}"
        print(error_message, file=sys.stderr)
        send_telegram_message(TELEGRAM_CHAT_ID, error_message, TELEGRAM_WEBHOOK_URL)
        sys.exit(1)

    if not ping_output:
        no_output_message = f"Ping to {TARGET_IP} completed, but no output captured."
        print(no_output_message, file=sys.stderr)
        send_telegram_message(TELEGRAM_CHAT_ID, no_output_message, TELEGRAM_WEBHOOK_URL)
        sys.exit(1)

    analysis_result = analyze_with_openai(ping_output, OPENAI_API_URL, OPENAI_API_KEY, OPENAI_MODEL)

    if analysis_result is None:
        ai_error_message = "Failed to call AI API for analysis, check logs."
        print(ai_error_message, file=sys.stderr)
        send_telegram_message(TELEGRAM_CHAT_ID, ai_error_message, TELEGRAM_WEBHOOK_URL)
        sys.exit(1)

    send_success = send_telegram_message(TELEGRAM_CHAT_ID, analysis_result, TELEGRAM_WEBHOOK_URL)

    if not send_success:
        print("Failed to send final analysis result to Telegram.", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)
