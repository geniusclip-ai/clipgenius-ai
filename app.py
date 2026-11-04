
import streamlit as st
from google import genai
import tempfile
import subprocess
import os
import json
import re
import time
import zipfile
from io import BytesIO
from urllib.parse import urlparse

# ---------------------------------
# CONFIGURATION
# ---------------------------------

st.set_page_config(
    page_title="ClipGenius AI",
    page_icon="🎬",
    layout="wide"
)

MODEL = "gemini-3.8-flash"

st.markdown("""
<style>
.main {
    background-color: #0e1117;
}
h1 {
    color: #a78bfa;
}
div.stButton > button {
    border-radius: 10px;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------
# HELPER FUNCTIONS
# ---------------------------------

def valid_youtube_url(url):
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()

        return (
            parsed.scheme in ("http", "https")
            and (
                host == "youtube.com"
                or host.endswith(".youtube.com")
                or host == "youtu.be"
            )
        )
    except Exception:
        return False


def get_video_duration(path):
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )

    return float(result.stdout.strip())


def extract_json(text):
    text = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        text.strip(),
        flags=re.IGNORECASE
    )

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("AI did not return valid JSON.")

    return json.loads(text[start:end + 1])


def analyze_video(client, video_path=None, youtube_url=None,
                  clip_count=5):

    prompt = f"""
You are ClipGenius AI, a professional YouTube Shorts
content strategist and video editor.

Analyze the supplied video carefully.

Find the {clip_count} strongest potential YouTube Shorts.

Prioritize:
1. Interesting or surprising moments.
2. Strong storytelling.
3. Useful educational information.
4. Funny or entertaining moments.
5. Emotional or engaging conversations.
6. Strong opening hooks.
7. Moments that make sense without excessive context.

CLIP REQUIREMENTS:

- Each clip should normally be 15-60 seconds.
- Do not invent dialogue or events.
- Start and end at meaningful moments.
- Avoid cutting sentences in the middle.
- Avoid selecting duplicate or heavily overlapping moments.
- Prefer clips that work independently.
- Rank clips by estimated audience appeal.
- Scores are estimates, not predictions of actual views.

For each clip provide:

start: timestamp in seconds (number)
end: timestamp in seconds (number)
score: estimated potential from 1 to 100
reason: why the moment is interesting
title: YouTube Shorts title
description: SEO-friendly description
hashtags: array of relevant hashtags
hook: opening text for the clip
keywords: relevant search keywords

Also provide:

- Overall video summary.
- Best target audience.
- Three future video ideas.
- Recommended upload strategy.
- Main topic/category.

Return ONLY valid JSON in this structure:

{{
  "summary": "Video summary",
  "category": "Video category",
  "target_audience": "Target audience",
  "clips": [
    {{
      "start": 10,
      "end": 40,
      "score": 92,
      "reason": "Reason for selection",
      "title": "Example title",
      "description": "Example description",
      "hashtags": ["#shorts", "#example"],
      "hook": "Opening hook",
      "keywords": ["example", "topic"]
    }}
  ],
  "future_ideas": [
    "Video idea 1",
    "Video idea 2",
    "Video idea 3"
  ],
  "upload_strategy": [
    "Recommendation 1",
    "Recommendation 2"
  ]
}}
"""

    if video_path:
        uploaded = client.files.upload(file=video_path)

        # Wait for Gemini video processing.
        start_wait = time.time()

        while True:
            uploaded = client.files.get(name=uploaded.name)
            state = uploaded.state.name

            if state == "ACTIVE":
                break

            if state == "FAILED":
                raise RuntimeError("Gemini video processing failed.")

            if time.time() - start_wait > 600:
                raise TimeoutError("Video processing took too long.")

            time.sleep(5)

        response = client.interactions.create(
            model=MODEL,
            input=[
                {
                    "type": "video",
                    "uri": uploaded.uri,
                    "mime_type": uploaded.mime_type,
                    "processing": "agentic"
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        )

    else:
        response = client.interactions.create(
            model=MODEL,
            input=[
                {
                    "type": "video",
                    "uri": youtube_url
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        )

    return extract_json(response.output_text)


def create_vertical_clip(source, output, start, end):
    duration = end - start

    # Center crop to 9:16.
    # This is a simple crop, not AI face tracking.

    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", source,
        "-t", str(duration),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1500:])


def build_zip(clips, analysis):
    memory_file = BytesIO()

    with zipfile.ZipFile(
        memory_file, "w", zipfile.ZIP_DEFLATED
    ) as archive:

        for filename, video_bytes in clips:
            archive.writestr(filename, video_bytes)

        archive.writestr(
            "content_strategy.json",
            json.dumps(analysis, indent=2)
        )

    memory_file.seek(0)
    return memory_file.getvalue()


# ---------------------------------
# WEBSITE HEADER
# ---------------------------------

st.title("🎬 ClipGenius AI")
st.subheader("Your Automatic YouTube Shorts Creator")

st.write(
    "Analyze long videos, discover interesting moments, "
    "create vertical clips and generate YouTube content."
)

st.divider()

# ---------------------------------
# SIDEBAR
# ---------------------------------

with st.sidebar:

    st.header("⚙️ AI Settings")

    api_key = st.text_input(
        "Gemini API Key",
        type="password"
    )

    clip_count = st.slider(
        "Number of clips",
        min_value=1,
        max_value=10,
        value=5
    )

    st.caption("Target format: YouTube Shorts 9:16")

    st.divider()

    st.info(
        "Your API key is used for this session. "
        "Do not share it or commit it to GitHub."
    )

# ---------------------------------
# VIDEO SOURCE
# ---------------------------------

st.header("📁 Choose Video Source")

source_type = st.radio(
    "Select input method",
    ["Upload Video", "YouTube Link"],
    horizontal=True
)

video_file = None
youtube_url = None

rights_confirmed = False

if source_type == "Upload Video":

    video_file = st.file_uploader(
        "Upload your original video",
        type=["mp4", "mov", "avi", "webm"]
    )

    rights_confirmed = st.checkbox(
        "I own this video or have permission to edit it."
    )

else:

    youtube_url = st.text_input(
        "Paste a public YouTube URL",
        placeholder="https://www.youtube.com/watch?v=..."
    )

    st.info(
        "YouTube URL mode analyzes public videos and generates "
        "clip timestamps and post recommendations. It does not "
        "download or cut YouTube-hosted content. Upload your "
        "authorized original video to generate clip files."
    )

st.divider()

# ---------------------------------
# AUTOMATIC ANALYSIS
# ---------------------------------

if st.button(
    "🚀 Analyze and Generate Clips",
    type="primary",
    use_container_width=True
):

    if not api_key:
        st.error("Enter your Gemini API key in the sidebar.")

    elif source_type == "Upload Video" and not video_file:
        st.error("Please upload a video.")

    elif source_type == "Upload Video" and not rights_confirmed:
        st.error("Please confirm that you have editing rights.")

    elif source_type == "YouTube Link" and not valid_youtube_url(
        youtube_url or ""
    ):
        st.error("Please enter a valid YouTube URL.")

    else:

        try:
            client = genai.Client(api_key=api_key)

            with tempfile.TemporaryDirectory() as temp_dir:

                input_path = None
                video_duration = None

                # Save uploaded video locally.

                if source_type == "Upload Video":

                    input_path = os.path.join(
                        temp_dir, "original_video.mp4"
                    )

                    with open(input_path, "wb") as f:
                        f.write(video_file.getbuffer())

                    video_duration = get_video_duration(input_path)

                # Analyze video.

                with st.spinner(
                    "🧠 Gemini is analyzing the video..."
                ):

                    analysis = analyze_video(
                        client=client,
                        video_path=input_path,
                        youtube_url=youtube_url,
                        clip_count=clip_count
                    )

                clips_data = analysis.get("clips", [])

                if not clips_data:
                    st.warning("No suitable clips were identified.")
                    st.stop()

                st.success("Video analysis completed!")

                generated_clips = []
                valid_recommendations = []

                # Automatically create all valid clips
                # for uploaded original videos.

                if input_path:

                    progress = st.progress(0)

                    for index, clip in enumerate(clips_data):

                        try:
                            start = float(clip["start"])
                            end = float(clip["end"])

                            if (
                                start < 0
                                or end <= start
                                or end - start > 60
                                or start >= video_duration
                                or end > video_duration
                            ):
                                continue

                            filename = f"Short_{index + 1}.mp4"

                            output_path = os.path.join(
                                temp_dir, filename
                            )

                            create_vertical_clip(
                                input_path,
                                output_path,
                                start,
                                end
                            )

                            with open(output_path, "rb") as f:
                                generated_clips.append(
                                    (filename, f.read())
                                )

                            valid_recommendations.append(clip)

                        except Exception as clip_error:
                            st.warning(
                                f"Clip {index + 1} skipped: "
                                f"{clip_error}"
                            )

                        progress.progress(
                            (index + 1) / len(clips_data)
                        )

                # Store result in session state.

                st.session_state["analysis"] = analysis
                st.session_state["clips"] = generated_clips
                st.session_state["recommendations"] = (
                    valid_recommendations
                )
                st.session_state["source_type"] = source_type

                if generated_clips:
                    st.session_state["zip_data"] = build_zip(
                        generated_clips,
                        analysis
                    )

        except Exception as error:
            st.error(f"Processing error: {error}")


# ---------------------------------
# DISPLAY RESULTS
# ---------------------------------

if "analysis" in st.session_state:

    result = st.session_state["analysis"]

    st.divider()
    st.header("📊 Video Analysis")

    st.write(result.get("summary", ""))

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Content Category",
            result.get("category", "Unknown")
        )

    with col2:
        st.write("**Target Audience**")
        st.write(result.get("target_audience", "General"))

    st.header("🔥 Recommended Shorts")

    recommendations = st.session_state.get(
        "recommendations", []
    )

    for index, clip in enumerate(recommendations):

        with st.expander(
            f"Clip {index + 1}: {clip.get('title', 'Untitled')}",
            expanded=True
        ):

            st.metric(
                "Estimated Content Score",
                f"{clip.get('score', 0)}/100"
            )

            st.write("**Timestamp**")
            st.write(
                f"{clip['start']}s – {clip['end']}s"
            )

            st.write("**Why this clip?**")
            st.write(clip.get("reason", ""))

            st.write("**Opening Hook**")
            st.write(clip.get("hook", ""))

            st.write("**YouTube Title**")
            st.write(clip.get("title", ""))

            st.write("**Description**")
            st.write(clip.get("description", ""))

            st.write("**Hashtags**")
            st.write(" ".join(clip.get("hashtags", [])))

            st.write("**Keywords**")
            st.write(", ".join(clip.get("keywords", [])))

    # Show automatically generated clips.

    generated = st.session_state.get("clips", [])

    if generated:

        st.header("🎞️ Your Generated Shorts")

        for filename, video_bytes in generated:

            with st.expander(filename):

                st.video(video_bytes)

                st.download_button(
                    "⬇️ Download This Short",
                    data=video_bytes,
                    file_name=filename,
                    mime="video/mp4",
                    key=f"download_{filename}"
                )

        st.download_button(
            "📦 Download ALL Shorts (ZIP)",
            data=st.session_state["zip_data"],
            file_name="ClipGenius_Shorts.zip",
            mime="application/zip",
            use_container_width=True
        )

    elif st.session_state.get("source_type") == "YouTube Link":

        st.info(
            "Analysis and timestamps are ready. "
            "Upload your authorized original video to create "
            "the actual MP4 clips."
        )

    st.divider()

    st.header("💡 Future Video Ideas")

    for idea in result.get("future_ideas", []):
        st.write("•", idea)

    st.header("📅 Upload Strategy")

    for recommendation in result.get("upload_strategy", []):
        st.write("•", recommendation)

    st.success("Your ClipGenius analysis is ready!")

