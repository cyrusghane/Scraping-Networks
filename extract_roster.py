#!/usr/bin/env python3
"""
extract_roster.py — pull a member roster out of a Slack screen-capture PDF.

A "screencapture" PDF of a Slack member list has no text layer — each page is a
JPEG image. This script extracts those embedded JPEGs (DCTDecode streams) without
needing poppler/pdf2image, so you can read them (e.g. with a vision model, or by
eye) and transcribe the names into a `Name` CSV that enrich.py consumes.

  python3 extract_roster.py "screencapture ... .pdf" out_dir/

Then read out_dir/page_*.jpg, transcribe to a CSV with at least a `Name` column
(a free-text hint column like a Slack status helps disambiguation a lot), and run
enrich.py over it.
"""

import os, sys


def extract_jpegs(pdf_path, out_dir):
    data = open(pdf_path, "rb").read()
    os.makedirs(out_dir, exist_ok=True)
    i = n = 0
    while True:
        d = data.find(b"/DCTDecode", i)
        if d == -1:
            break
        s = data.find(b"stream", d)
        j = s + len("stream")
        if data[j:j + 2] == b"\r\n":
            j += 2
        elif data[j:j + 1] in (b"\n", b"\r"):
            j += 1
        e = data.find(b"endstream", j)
        jpeg = data[j:e].rstrip(b"\r\n")
        n += 1
        path = os.path.join(out_dir, f"page_{n:02d}.jpg")
        open(path, "wb").write(jpeg)
        print("wrote", path, f"({len(jpeg)} bytes)")
        i = e + 1
    return n


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: python3 extract_roster.py <slack_screencapture.pdf> <out_dir>")
    n = extract_jpegs(sys.argv[1], sys.argv[2])
    if not n:
        sys.exit("No DCTDecode (JPEG) images found — is this a screen-capture PDF?")
    print(f"\nExtracted {n} page image(s). Read them, transcribe names to a CSV, then run enrich.py.")


if __name__ == "__main__":
    main()
