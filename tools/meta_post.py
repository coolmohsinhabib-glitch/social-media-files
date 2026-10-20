#!/usr/bin/env python3
"""Post to Mohsin's Facebook Page and Instagram through the Meta Graph API.

Tokens are NEVER stored in this repo. Pass the token file (a text file with lines
"Page token - personal: EAA..." and "Page token - IDB: EAA...") with --tokens.
Nothing here prints a token.

Commands (all print JSON results):
  ig-reel-container  --video URL --caption TEXT [--collab user1,user2] [--cover-ms N]
                     -> creates a Reel container (not yet published); prints container id + status
  ig-status          --id CONTAINER_ID
  ig-publish         --id CONTAINER_ID              -> publishes a FINISHED container; prints media id + permalink
  ig-story           --video URL | --image URL      -> creates and publishes a Story (waits for processing)
  fb-reel            --video URL --caption TEXT [--at "YYYY-MM-DDTHH:MM" PKT]  -> Page Reel, now or scheduled
  fb-video           --video URL --caption TEXT [--at "YYYY-MM-DDTHH:MM" PKT]  -> Page video via graph.facebook.com (works from the workspace; fb-reel needs rupload.facebook.com)
  fb-story           --video URL | --image URL      -> Page Story
  ig-carousel        --images URL1,URL2,... --caption TEXT [--collab u1,u2]
                     -> creates a CAROUSEL container (2-10 images), waits for FINISHED; publish later with ig-publish
  fb-photos          --images URL1,URL2,... --caption TEXT [--at "YYYY-MM-DDTHH:MM" PKT]
                     -> multi-photo Page post (carousel-style), now or scheduled
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

V = "v26.0"
G = f"https://graph.facebook.com/{V}"
PAGE_ID = "1392964837235130"          # Mohsin Habib - eBay Seller - Trainer
IG_ID = "17841478792000387"           # @mohsin__habib
PKT = timezone(timedelta(hours=5))


def load_token(path, label="Page token - personal"):
    for line in open(path, encoding="utf-8"):
        if line.strip().lower().startswith(label.lower()):
            m = re.search(r"EAA[A-Za-z0-9]+", line)
            if m:
                return m.group(0)
    sys.exit(f"token '{label}' not found in token file")


def call(method, url, token, params=None, headers=None):
    data = None
    params = dict(params or {})
    if method == "GET":
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    h = {"Authorization": "Bearer " + token}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e)
        except Exception:
            err = {"error": {"message": str(e)}}
        return err


def wait_container(cid, token, tries=40, delay=6):
    st = {}
    for _ in range(tries):
        st = call("GET", f"{G}/{cid}", token, {"fields": "status_code,status"})
        if st.get("status_code") in ("FINISHED", "ERROR", "EXPIRED", "PUBLISHED"):
            return st
        time.sleep(delay)
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("--tokens", required=True)
    ap.add_argument("--video"); ap.add_argument("--image"); ap.add_argument("--caption", default="")
    ap.add_argument("--collab", default=""); ap.add_argument("--cover-ms", type=int)
    ap.add_argument("--id"); ap.add_argument("--at"); ap.add_argument("--images", default="")
    a = ap.parse_args()
    tok = load_token(a.tokens)
    out = {}
    if a.cmd == "ig-reel-container":
        p = {"media_type": "REELS", "video_url": a.video, "caption": a.caption, "share_to_feed": "true"}
        if a.collab:
            p["collaborators"] = json.dumps([u.strip() for u in a.collab.split(",") if u.strip()])
        if a.cover_ms is not None:
            p["thumb_offset"] = str(a.cover_ms)
        r = call("POST", f"{G}/{IG_ID}/media", tok, p)
        out = {"create": r}
        if "id" in r:
            out["status"] = wait_container(r["id"], tok)
    elif a.cmd == "ig-status":
        out = call("GET", f"{G}/{a.id}", tok, {"fields": "status_code,status"})
    elif a.cmd == "ig-publish":
        r = call("POST", f"{G}/{IG_ID}/media_publish", tok, {"creation_id": a.id})
        out = {"publish": r}
        if "id" in r:
            out["media"] = call("GET", f"{G}/{r['id']}", tok, {"fields": "permalink,timestamp"})
    elif a.cmd == "ig-story":
        p = {"media_type": "STORIES"}
        if a.video: p["video_url"] = a.video
        else: p["image_url"] = a.image
        r = call("POST", f"{G}/{IG_ID}/media", tok, p)
        out = {"create": r}
        if "id" in r:
            st = wait_container(r["id"], tok); out["status"] = st
            if st.get("status_code") == "FINISHED":
                out["publish"] = call("POST", f"{G}/{IG_ID}/media_publish", tok, {"creation_id": r["id"]})
    elif a.cmd == "fb-reel":
        start = call("POST", f"{G}/{PAGE_ID}/video_reels", tok, {"upload_phase": "start"})
        out = {"start": {k: v for k, v in start.items() if k != "upload_url"}}
        vid = start.get("video_id")
        if vid:
            req = urllib.request.Request(f"https://rupload.facebook.com/video-upload/{V}/{vid}", method="POST",
                                         headers={"Authorization": "OAuth " + tok, "file_url": a.video})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    out["upload"] = json.load(r)
            except urllib.error.HTTPError as e:
                out["upload"] = {"error": e.read().decode()[:500]}
            fin = {"upload_phase": "finish", "video_id": vid, "description": a.caption}
            if a.at:
                ts = int(datetime.strptime(a.at, "%Y-%m-%dT%H:%M").replace(tzinfo=PKT).timestamp())
                fin.update({"video_state": "SCHEDULED", "scheduled_publish_time": str(ts)})
            else:
                fin["video_state"] = "PUBLISHED"
            out["finish"] = call("POST", f"{G}/{PAGE_ID}/video_reels", tok, fin)
            out["video_id"] = vid
    elif a.cmd == "fb-video":
        # Page video via graph.facebook.com (file_url); vertical short videos show in Reels.
        p = {"file_url": a.video, "description": a.caption}
        if a.at:
            ts = int(datetime.strptime(a.at, "%Y-%m-%dT%H:%M").replace(tzinfo=PKT).timestamp())
            p.update({"published": "false", "scheduled_publish_time": str(ts)})
        out = call("POST", f"{G}/{PAGE_ID}/videos", tok, p)
    elif a.cmd == "fb-story":
        if a.video:
            start = call("POST", f"{G}/{PAGE_ID}/video_stories", tok, {"upload_phase": "start"})
            vid = start.get("video_id"); out = {"start": {k: v for k, v in start.items() if k != "upload_url"}}
            if vid:
                req = urllib.request.Request(f"https://rupload.facebook.com/video-upload/{V}/{vid}", method="POST",
                                             headers={"Authorization": "OAuth " + tok, "file_url": a.video})
                with urllib.request.urlopen(req, timeout=300) as r:
                    out["upload"] = json.load(r)
                out["finish"] = call("POST", f"{G}/{PAGE_ID}/video_stories", tok, {"upload_phase": "finish", "video_id": vid})
        else:
            ph = call("POST", f"{G}/{PAGE_ID}/photos", tok, {"url": a.image, "published": "false"})
            out = {"photo": ph}
            if "id" in ph:
                out["story"] = call("POST", f"{G}/{PAGE_ID}/photo_stories", tok, {"photo_id": ph["id"]})
    elif a.cmd == "ig-carousel":
        urls = [u.strip() for u in a.images.split(",") if u.strip()]
        kids = []
        for u in urls:
            r = call("POST", f"{G}/{IG_ID}/media", tok, {"image_url": u, "is_carousel_item": "true"})
            if "id" not in r:
                out = {"child_error": r, "url": u}; print(json.dumps(out, indent=1)); return
            kids.append(r["id"])
        for k in kids:
            wait_container(k, tok, tries=20, delay=3)
        p = {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": a.caption}
        if a.collab:
            p["collaborators"] = json.dumps([u.strip() for u in a.collab.split(",") if u.strip()])
        r = call("POST", f"{G}/{IG_ID}/media", tok, p)
        out = {"children": kids, "create": r}
        if "id" in r:
            out["status"] = wait_container(r["id"], tok)
    elif a.cmd == "fb-photos":
        urls = [u.strip() for u in a.images.split(",") if u.strip()]
        ids = []
        for u in urls:
            r = call("POST", f"{G}/{PAGE_ID}/photos", tok, {"url": u, "published": "false", "temporary": "true" if a.at else "false"})
            if "id" not in r:
                out = {"photo_error": r, "url": u}; print(json.dumps(out, indent=1)); return
            ids.append(r["id"])
        p = {"message": a.caption}
        for i, pid in enumerate(ids):
            p[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
        if a.at:
            ts = int(datetime.strptime(a.at, "%Y-%m-%dT%H:%M").replace(tzinfo=PKT).timestamp())
            p.update({"published": "false", "scheduled_publish_time": str(ts)})
        out = {"photos": ids, "post": call("POST", f"{G}/{PAGE_ID}/feed", tok, p)}
    else:
        sys.exit("unknown command")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
