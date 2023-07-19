import re
import time
import json
import base64
import subprocess
import random
import praw
import sqlite3
import os
from tiktok_uploader.upload import upload_videos
from tiktok_uploader.auth import AuthBackend
from google.cloud import texttospeech_v1beta1 as tts
from enum import Enum

class Mode(Enum):
    API = 0
    MANUAL = 1
    TESTING = 2

def post_to_ssml(split_post):
    ssml_text = ""
    i = 0

    for phrase in split_post:
        processed_phrase = phrase.replace("/", " slash ").replace("-", " ").replace("*", "").replace("&", " and ")
        processed_phrase = re.sub("(?<=[0-9])\.(?=[0-9])", " point ", processed_phrase) # Replace decimal points in numbers with the word "point"
        ssml_text += "<mark name='" + str(i) + "'/>" + processed_phrase
        i += 1

    return "<speak>" + ssml_text + "<mark name='" + str(i) + "'/>" + "</speak>"

def google_api_request(ssml_text):
    client = tts.TextToSpeechClient()
    voice = tts.VoiceSelectionParams(language_code="en-US", name="en-US-Standard-J")
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.MP3_64_KBPS, pitch=-5.0, speaking_rate=1.3)

    return client.synthesize_speech(
        request=tts.SynthesizeSpeechRequest(
            input=tts.SynthesisInput(ssml=ssml_text),
            voice=voice,
            audio_config=audio_config,
            enable_time_pointing = [tts.SynthesizeSpeechRequest.TimepointType.SSML_MARK]
        )
    )

def manual_request(ssml_text):

    data = {
        "audioConfig": {
            "audioEncoding": "MP3_64_KBPS",
            "pitch": -5.0,
            "speakingRate": 1.3
        },
        "input": {
            "ssml": ssml_text
        },
        "voice": {
            "languageCode": "en-US",
            "name": "en-US-Standard-J"
        },
        "enableTimePointing": [
            "SSML_MARK"
        ]
    }

    with open("intermediates/JSON_copy_paste.txt", "w") as f:
        json.dump(data, f)

    input("Paste the response into JSON_copy_paste.txt and hit enter")
    
def save_audio(binary_audio):    
    with open("intermediates/voice.mp3", "wb") as out:
        out.write(binary_audio)

def break_long_phrases(split_post):
    i = 0
    # Loop over every phrase in split_post
    while i < len(split_post):
        # print("i = " + str(i))
        # print("list length = " + str(len(split_post)))
        current = split_post[i]
        # If one phrase is over 55 characters,
        if len(current) > 55:
            # remove that phrase from the list,
            split_post.pop(i)
            # and split it into words
            words = current.split()
            # Add the words back in 6 at a time
            while len(words) > 6:
                split_post.insert(i, " ".join(words[-6:]))
                del words[-6:]
            # Add the remaining words in
            split_post.insert(i, " ".join(words))
        i += 1

def sec_to_hmsm(sec):
    return sec_to_hms(sec) + "," + (f"{sec:.3f}")[-3:]

def sec_to_hms(sec):
    return time.strftime("%H:%M:%S", time.gmtime(sec))

def create_subtitles(split_post, times):
    with open("intermediates/subtitles.srt", "w", encoding="utf-8") as f:
        for i in range(len(split_post)):
            if i + 1 >= len(times) or i != int(times[i]["markName"]):
                print_error("***Error in timepoints from API response***")
                cursor.execute("INSERT INTO Posts (name, uploaded) VALUES (?, ?)", (post_id, 0))
                save_and_quit()
            start = times[i]["timeSeconds"]
            end = times[i + 1]["timeSeconds"]
            f.write(str(i + 1) + "\n" + sec_to_hmsm(start) + " --> " + sec_to_hmsm(end) + "\n" + split_post[i].strip() + "\n\n")

def get_file_length(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=True)
    return float(result.stdout)

def print_error(string):
    print('\033[91m' + string + '\033[0m')

def save_and_quit():
    cursor.close()
    connection.commit()
    connection.close()
    quit()

# Set program mode
current_mode = Mode.API

# Make result and intermediates folders if they don't exist
os.makedirs("result", exist_ok=True)
os.makedirs("intermediates", exist_ok=True)

# Create/connect to database of already processed posts
connection = sqlite3.connect("result/posts.sqlite")
cursor = connection.cursor()

# Create table in the database if it doesn't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS "Posts" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT UNIQUE,
	"uploaded"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
);''')

# Create Reddit instance
reddit = praw.Reddit("bot1")

# Query for checking if a given post is in the database
select_query = "SELECT * FROM Posts WHERE name = ?"

# Loop over popular posts
# for submission in reddit.subreddit("AmITheAsshole").top(time_filter="year"):
for submission in reddit.subreddit("AmITheAsshole").hot():
    post_id = submission.name
    # Check that post has not already been used
    if not cursor.execute(select_query, [post_id]).fetchall():
        # Check that post is not sticked and doesn't contain a link
        if not submission.stickied and "http" not in submission.selftext:
            # Save post text
            post_text = submission.title + " " + submission.selftext
            break

post_text = post_text.strip() + "." # Ensure text ends with punctuation so that the last phrase is captured
post_text = post_text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"') # Swap out unusual quotation marks
post_text = re.sub("\s*\n", ". ", post_text) # Replace paragraph breaks with periods
split_post = re.findall("[^.]+?[.,?!][0-9!?)\"']*", post_text) # Split post into phrases followed by punctuation
break_long_phrases(split_post)

# Convert split-up post into ssml
ssml_text = post_to_ssml(split_post)

if current_mode == Mode.API:

    # If in API mode, send ssml to google API and save response
    response = google_api_request(ssml_text)
    # Save audio to file
    save_audio(response.audio_content)
    # Convert response timepoints data structure to list of dictionaries
    times = []
    for timepoint in response.timepoints:
        times.append({"markName": timepoint.mark_name, "timeSeconds": timepoint.time_seconds})

    # Write API response to file as JSON for debugging and testing
    with open("intermediates/JSON_copy_paste.txt", "w") as f:
        json.dump({"audioContent": base64.b64encode(response.audio_content).decode(), "timepoints": times}, f)
    
else:
    
    # If in manual mode, write JSON request to file and prompt response to be copied back in
    if current_mode == Mode.MANUAL:
        manual_request(ssml_text)

    # Read copied response from file
    with open("intermediates/JSON_copy_paste.txt", "r") as f:
        response = json.load(f)
    
    # Decode and store audio and save timepoints
    save_audio(base64.b64decode(response["audioContent"]))
    times = response["timepoints"]

# Choose a random video to use from the background_videos folder
bg_video_name = random.choice(os.listdir("background_videos"))

# Get the lengths of the background video and TTS audio
video_length = get_file_length("background_videos/" + bg_video_name)
audio_length = get_file_length("intermediates/voice.mp3")

# End program if the video is too long to upload to TikTok
if audio_length >= 180:
    print_error("***Video over 3 minutes***")
    cursor.execute("INSERT INTO Posts (name, uploaded) VALUES (?, ?)", (post_id, 0))
    save_and_quit()

# Generate srt file from timepoints
create_subtitles(split_post, times)

# Combine TTS audio with random section of the background video
subprocess.run("ffmpeg -y -ss " + sec_to_hms(random.randrange(0, int(video_length - audio_length - 1)))
               + " -i background_videos/" + bg_video_name +
               " -i intermediates/voice.mp3 -c copy -map 0:v:0 -map 1:a:0 -shortest intermediates/video_no_text.mp4", shell=True)

# Use ffmpeg subtitles filter to add text onto the video when it's spoken
subprocess.run("ffmpeg -y -i intermediates/video_no_text.mp4 -vf \"subtitles=intermediates/subtitles.srt:force_style='Fontname=Montserrat Black,Alignment=10,Shadow=1,MarginL=90,MarginR=90'\" -c:a copy result/final.mov", shell=True)

# Upload the final video to TikTok, storing it into failed_videos if it doesn't upload
failed_videos = upload_videos([{"path": "result/final.mov", "description": "#reddit #reddittiktok #redditreading #redditposts #redditstories #fyp #xyzbca "}],
              auth=AuthBackend(cookies="private/cookies.txt"), headless=True)

# If the video is successfully uploaded, add its id to the database
if not failed_videos:
    cursor.execute("INSERT INTO Posts (name, uploaded) VALUES (?, ?)", (post_id, 1))

# Commit and close the database
save_and_quit()
