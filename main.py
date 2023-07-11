import re
import time
import requests
import json
import base64
import subprocess
import random

def post_to_ssml(split_post):
    ssml_text = ""
    i = 0

    for phrase in split_post:
        ssml_text += "<mark name='" + str(i) + "'/>" + phrase.replace("/", " slash ").replace('"', "'")
        i += 1

    return "<speak>" + ssml_text + "<mark name='" + str(i) + "'/>" + "</speak>"

def google_api_request(ssml_text):

    url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize?key=[YOUR_API_KEY]"
    headers = {
        "Authorization": "Bearer [YOUR_ACCESS_TOKEN]",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

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

    return requests.post(url, headers=headers, data=data)

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

    with open("JSON_copy_paste.txt", "w") as f:
        json.dump(data, f)

    input("Paste the response into JSON_copy_paste.txt and hit enter")

    with open("JSON_copy_paste.txt", "r") as f:
        return json.load(f)
    
def decode_audio(base64_audio):
    audio = base64.b64decode(base64_audio)
    with open("voice.mp3", "wb") as out:
        out.write(audio)

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
    with open("subtitles.srt", "w") as f:
        for i in range(len(split_post)):
            start = times[i]["timeSeconds"]
            end = times[i + 1]["timeSeconds"]
            f.write(str(i + 1) + "\n" + sec_to_hmsm(start) + " --> " + sec_to_hmsm(end) + "\n" + split_post[i].strip() + "\n\n")

def get_file_length(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)

def print_error(string):
    print('\033[91m' + string + '\033[0m')

post_text = '''
Reddit post
'''

post_text += "."
post_text = post_text.replace("’", "'").replace("‘", "'")
split_post = re.findall(".+?[.,?!-]", post_text)
break_long_phrases(split_post)

ssml_text = post_to_ssml(split_post)

#######################################################

# API request
# response = google_api_request(ssml_text)

# Manual request
response = manual_request(ssml_text)

# Testing
# with open("JSON_copy_paste.txt", "r") as f:
#     response = json.load(f)

#######################################################

if "error" in response:
    print_error("****Google Cloud TTS API error****")
    quit()

bg_video_name = random.choice(["minecraft.mp4", "subway.mp4"])
video_length = get_file_length(bg_video_name)
audio_length = get_file_length("voice.mp3")

decode_audio(response["audioContent"])
subprocess.run("ffmpeg -y -ss " + sec_to_hms(random.randrange(0, int(video_length - audio_length - 1)))
               + " -i " + bg_video_name + " -i voice.mp3 -c copy -map 0:v:0 -map 1:a:0 -shortest video_no_text.mp4")

times = response["timepoints"]
create_subtitles(split_post, times)

subprocess.run("ffmpeg -y -i video_no_text.mp4 -vf \"subtitles=subtitles.srt:force_style='Fontname=Montserrat Black,Alignment=10,Shadow=1,MarginL=90,MarginR=90:charenc=ISO8859-1'\" -c:a copy final.mov")

# TODO: add reddit api integration
