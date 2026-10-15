#!/usr/bin/env python3
"""Ask a local open-source LLM (via Ollama) what the speaker of a text might be feeling.

Usage:
    python feelings.py "I can't believe they cancelled again."
    python feelings.py --file notes.txt
    echo "some text" | python feelings.py
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2"
QUESTION = "what are the possible feelings of the speaker?"


def read_text(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return f.read().strip()
    if args.text:
        return " ".join(args.text).strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return ""


def build_prompt(text):
    return f'Text:\n"""\n{text}\n"""\n\n{QUESTION}'


def stream_response(prompt, model, url):
    payload = json.dumps({"model": model, "prompt": prompt, "stream": True}).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request) as response:
        for line in response:
            if not line.strip():
                continue
            chunk = json.loads(line)
            if "error" in chunk:
                raise RuntimeError(chunk["error"])
            print(chunk.get("response", ""), end="", flush=True)
            if chunk.get("done"):
                break
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("text", nargs="*", help="text to analyze (or use --file / stdin)")
    parser.add_argument("--file", "-f", help="read text from a file")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--url", default=OLLAMA_URL, help="Ollama generate endpoint")
    args = parser.parse_args()

    text = read_text(args)
    if not text:
        parser.error("no text provided (pass it as an argument, with --file, or via stdin)")

    try:
        stream_response(build_prompt(text), args.model, args.url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit(f"Model '{args.model}' not found. Run: ollama pull {args.model}")
        sys.exit(f"Ollama returned HTTP {e.code}: {e.reason}")
    except urllib.error.URLError:
        sys.exit("Could not reach Ollama. Install it from https://ollama.com and run: ollama serve")
    except RuntimeError as e:
        sys.exit(f"Ollama error: {e}")


if __name__ == "__main__":
    main()
