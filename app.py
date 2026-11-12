import os, json, re, uuid, subprocess, shutil
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).resolve().parent
OUT = BASE / "outputs"
OUT.mkdir(exist_ok=True)
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret")

def safe_name(s):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-")[:45] or "video"

def ai_plan(topic, platform, duration, style, audience, language):
    """Create a script and scene plan. Uses OpenAI when an API key is configured."""
    key = os.getenv("OPENAI_API_KEY")
    if key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            prompt = f"""
Buat rancangan video dalam bahasa {language}. Kembalikan JSON valid saja dengan struktur:
{{"title":"...", "hook":"...", "narration":"...", "caption":"...", "hashtags":["..."],
"scenes":[{{"visual":"deskripsi visual rinci", "voiceover":"kalimat narasi adegan", "image_prompt":"prompt gambar sinematik dalam bahasa Inggris"}}]}}
Topik: {topic}
Platform: {platform}; durasi target: {duration}; gaya: {style}; target: {audience}.
Buat 4 sampai 8 adegan. Narasi harus natural, faktual, dan cocok dengan durasi.
"""
            response = client.responses.create(model=model, input=prompt)
            raw = response.output_text.strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
            data = json.loads(raw)
            if data.get("scenes"):
                return data
        except Exception as e:
            print("OpenAI plan error:", e)

    # Fallback works without API key
    scenes = [
        ("Pembuka yang menarik perhatian", f"Visual pembuka yang kuat tentang {topic}."),
        ("Pengenalan topik", f"Perkenalkan {topic} dengan visual yang jelas dan menarik."),
        ("Penjelasan utama", f"Tampilkan detail utama dan manfaat dari {topic}."),
        ("Contoh atau bukti", f"Tampilkan contoh nyata yang relevan dengan {topic}."),
        ("Penutup dan ajakan", f"Akhiri video tentang {topic} dengan ajakan bertindak.")
    ]
    return {
        "title": topic,
        "hook": f"Ada hal menarik tentang {topic} yang perlu Anda ketahui!",
        "narration": " ".join(x[1] for x in scenes),
        "caption": f"Yuk, kenali {topic}! Simak sampai selesai dan bagikan video ini.",
        "hashtags": ["#VideoAI", "#KontenKreator", "#Indonesia"],
        "scenes": [
            {"visual": name, "voiceover": desc,
             "image_prompt": f"Cinematic high quality visual about {topic}, {desc}, {style}, no text, 16:9"}
            for name, desc in scenes
        ]
    }

def create_scene_image(prompt, path, index):
    key = os.getenv("OPENAI_API_KEY")
    if key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            result = client.images.generate(
                model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
                prompt=prompt,
                size="1536x1024"
            )
            import base64
            path.write_bytes(base64.b64decode(result.data[0].b64_json))
            return
        except Exception as e:
            print("Image generation error:", e)
    # Local fallback image, so the project can still render without image API access.
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1280, 720), (18 + index*8, 35 + index*5, 70 + index*7))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except Exception:
        font = ImageFont.load_default()
    draw.text((70, 270), f"ADEGAN {index+1}", fill="white", font=font)
    draw.text((70, 350), prompt[:90], fill=(220,230,255))
    img.save(path)

def make_voice(text, path, voice):
    try:
        import asyncio, edge_tts
        async def run():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(path))
        asyncio.run(run())
        return True
    except Exception as e:
        print("TTS error:", e)
        return False

def probe_duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    try:
        return float(p.stdout.strip())
    except Exception:
        return 60.0

def make_srt(scene_texts, total_seconds, path):
    words = [max(1, len(t.split())) for t in scene_texts]
    total = sum(words)
    cursor = 0.0
    def stamp(sec):
        ms = int(round(sec * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    chunks = []
    for i, txt in enumerate(scene_texts, 1):
        end = cursor + total_seconds * words[i-1] / total
        chunks.append(f"{i}\n{stamp(cursor)} --> {stamp(end)}\n{txt}\n")
        cursor = end
    path.write_text("\n".join(chunks), encoding="utf-8")

def render_video(job_dir, image_paths, audio_path, srt_path, output_path):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg belum terpasang. Jalankan: sudo apt install ffmpeg")
    concat = job_dir / "images.txt"
    # concat demuxer: image durations proportional to voice-over length
    audio_len = probe_duration(audio_path) if audio_path.exists() else 45
    per = max(3.0, audio_len / max(1, len(image_paths)))
    lines = []
    for img in image_paths:
        lines += [f"file '{img.as_posix()}'", f"duration {per:.3f}"]
    lines.append(f"file '{image_paths[-1].as_posix()}'")
    concat.write_text("\n".join(lines), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat)]
    if audio_path.exists():
        cmd += ["-i", str(audio_path)]
    # Burn subtitles if available; escape path for ffmpeg filter syntax.
    subtitle_filter = ""
    if srt_path.exists():
        sp = str(srt_path).replace("\\", "/").replace(":", r"\:")
        subtitle_filter = f"subtitles='{sp}':force_style='FontName=DejaVu Sans,FontSize=22,Outline=2,Shadow=1,Alignment=2,MarginV=35'"
    vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    if subtitle_filter:
        vf += "," + subtitle_filter
    cmd += ["-vf", vf, "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium"]
    if audio_path.exists():
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", str(output_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-1800:])

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        topic = request.form.get("topic", "").strip()
        if not topic:
            flash("Topik video wajib diisi.")
            return redirect(url_for("index"))
        job_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:5]
        job_dir = OUT / job_id
        job_dir.mkdir(parents=True)
        platform = request.form.get("platform", "TikTok")
        duration = request.form.get("duration", "60 detik")
        style = request.form.get("style", "Cinematic")
        audience = request.form.get("audience", "Umum")
        language = request.form.get("language", "Bahasa Indonesia")
        voice = request.form.get("voice", "id-ID-ArdiNeural")
        try:
            plan = ai_plan(topic, platform, duration, style, audience, language)
            (job_dir / "project.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            (job_dir / "naskah.txt").write_text(
                f"{plan.get('title', topic)}\n\n{plan.get('narration','')}\n\n{plan.get('caption','')}\n{' '.join(plan.get('hashtags', []))}",
                encoding="utf-8"
            )
            image_paths = []
            for i, scene in enumerate(plan["scenes"]):
                p = job_dir / f"scene-{i+1:02}.png"
                create_scene_image(scene.get("image_prompt", scene.get("visual", topic)), p, i)
                image_paths.append(p)
            narration = " ".join(s.get("voiceover", "") for s in plan["scenes"] if s.get("voiceover")) or plan.get("narration", topic)
            audio = job_dir / "voiceover.mp3"
            has_audio = make_voice(narration, audio, voice)
            texts = [s.get("voiceover", "") for s in plan["scenes"] if s.get("voiceover")]
            if not texts:
                texts = [narration]
            srt = job_dir / "subtitle.srt"
            length = probe_duration(audio) if has_audio else max(30, len(narration.split())/2.5)
            make_srt(texts, length, srt)
            video = job_dir / "hasil-video.mp4"
            render_video(job_dir, image_paths, audio if has_audio else job_dir / "missing.mp3", srt, video)
            flash("Video berhasil dibuat.")
            return redirect(url_for("result", job_id=job_id))
        except Exception as e:
            (job_dir / "error.txt").write_text(str(e), encoding="utf-8")
            flash(f"Proses belum selesai: {e}")
            return redirect(url_for("result", job_id=job_id))
    return render_template("index.html", api_ready=bool(os.getenv("OPENAI_API_KEY")))

@app.route("/result/<job_id>")
def result(job_id):
    job_dir = OUT / safe_name(job_id)
    if not job_dir.exists():
        flash("Proyek tidak ditemukan.")
        return redirect(url_for("index"))
    plan_file = job_dir / "project.json"
    plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
    return render_template("result.html", job_id=job_id, plan=plan,
                           video=(job_dir / "hasil-video.mp4").exists(),
                           error=(job_dir / "error.txt").read_text(encoding="utf-8") if (job_dir / "error.txt").exists() else None,
                           files=[p.name for p in job_dir.iterdir() if p.is_file()])

@app.route("/download/<job_id>/<filename>")
def download(job_id, filename):
    job_dir = OUT / safe_name(job_id)
    return send_from_directory(job_dir, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
