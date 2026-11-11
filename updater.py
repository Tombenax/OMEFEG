
import requests
import zipfile
from io import BytesIO
import os

repo = "Tombenax/OMEFEG"
branch = "main"

sha_file = "last_commit.txt"

api_url = f"https://api.github.com/repos/{repo}/commits/{branch}"

response = requests.get(api_url)
response.raise_for_status()

latest_sha = response.json()["sha"]

print(f"Latest GitHub commit: {latest_sha}")

if os.path.exists(sha_file):
    with open(sha_file, "r") as f:
        downloaded_sha = f.read().strip()
else:
    downloaded_sha = ""

print(f"Downloaded commit:   {downloaded_sha or 'None'}")

if latest_sha == downloaded_sha:
    print("\nAlready up to date!")
    exit()

print("\nNew commit found! Downloading...")

url = f"https://github.com/{repo}/archive/{latest_sha}.zip"

response = requests.get(url)
response.raise_for_status()

with zipfile.ZipFile(BytesIO(response.content)) as z:

    for file_name in z.namelist():

        if file_name.endswith("/"):
            continue

        relative_path = file_name.split("/", 1)[1]

        if relative_path == "updater.py":
            continue

        dirname = os.path.dirname(relative_path)

        if dirname:
            os.makedirs(dirname, exist_ok=True)

        with open(relative_path, "wb") as f:
            f.write(z.read(file_name))

        print(f"Downloaded: {relative_path}")

with open(sha_file, "w") as f:
    f.write(latest_sha)

print(f"\nRepository updated successfully!")
print(f"New commit: {latest_sha}")
