## import gevent.monkey
# #gevent.monkey.patch_all(thread=False, select=False)
import grequests
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
import urllib
import uuid
import os
import time
import datetime
from io import BytesIO
from selenium.webdriver.chrome import webdriver
from selenium import webdriver
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from dotenv import load_dotenv
import requests
import json
from flask import Flask, request
import cloudscraper
import cloudinary
import cloudinary.uploader
import cloudinary.api
from pymongo import MongoClient
import sys
from imagekitio import ImageKit
from PIL import Image
import base64
import urllib.request

load_dotenv()
app = Flask(__name__)
cloud_name = os.getenv('cloud_name')
api_key = os.getenv('api_key')
api_secret = os.getenv('api_secret')
MONGODB = os.getenv('MONGODB')
client = MongoClient(MONGODB)
# db = client['guard_design_dev']
db = client['guard-design']
config = cloudinary.config(cloud_name=cloud_name,
                           api_key=api_key,
                           api_secret=api_secret,
                           secure=True)


# 1) https://www.artstation.com/users/<username>/projects.json
# 2) for each project copy in a variable hash_id
# 3) download the json from https://www.artstation.com/projects/<hash_id>.json


#
counter_fails = 0

@app.route('/scrape_user',
           methods=['POST'])  # description - Each hash_id contains all the documents of the specified project
def scrape_username():  # inputs - username
    try:
        data = request.json
        username = str(data['username'])
        owner_id = data['owner_id']
        email = data['email']
        scraper = cloudscraper.create_scraper()  # returns a CloudScraper instance
        projects_text = scraper.get('https://www.artstation.com/users/' + username + '/projects.json').text
        projects_data = json.loads(projects_text)
        array_of_projects = projects_data['data']
        documents_of_each_project = []
        set_of_each_project = {}
        # get all projects of the specified user and save links to each project
        for project in array_of_projects:
            hash_id = project['hash_id']
            current_link = 'https://www.artstation.com/projects/'
            current_link += hash_id + '.json'
            documents_of_each_project.append({'hash_id': hash_id, 'link': current_link})
        # get all documents of each project (images etc.)
        for current_hash_obj in documents_of_each_project:
            project_page_data = scraper.get(current_hash_obj['link']).text
            documents_of_project = json.loads(project_page_data)
            # arrays_of_each_project.append({current_hash_obj['hash_id'] : documents_of_project})
            set_of_each_project[current_hash_obj['hash_id']] = documents_of_project
        projects = []
        for project in array_of_projects:
            file_type = project['cover']['thumb_url'].split('.')[-1]
            obj_of_uploaded_file_to_append = upload_image_to_imagekit(username + '-' + '.' + file_type,
                                                                      project['cover']['thumb_url'])
            projects.append(
                add_project(project['title'], email, owner_id, obj_of_uploaded_file_to_append, set_of_each_project,
                            project['hash_id']))
        db['projects'].insert_many(projects)
        return "Done"
    except:
        if counter_fails < 10:
            scrape_username()
        else:
            return "Done"


def add_files(hash_id, uid, owner_email, set_of_each_project):
    array_of_files = []
    ref_ids = []
    position = 0
    time_ms = int(datetime.datetime.now().timestamp() * 1000)
    image_urls = [url['image_url'] for url in set_of_each_project[hash_id]['assets']]
    for image_url_to_upload in image_urls:
        file_type = image_url_to_upload.split('/')[-1]
        obj_uploaded_file = upload_image_to_imagekit(uid + '-' + str(uuid.uuid4()) + '.' + file_type,
                                                     image_url_to_upload)
        obj_uploaded_file['ownerId'] = uid
        obj_uploaded_file['owner'] = owner_email
        obj_uploaded_file['lastModified'] = time_ms
        obj_uploaded_file['caption'] = ''
        obj_uploaded_file['position'] = position
        position += 1
        array_of_files.append(obj_uploaded_file)
    for file in array_of_files:
        result = db['files'].insert_one(file)
        ref_ids.append(result.inserted_id)
    return ref_ids


def add_project(title, email, owner_id, obj_of_uploaded_file_to_append, set_of_each_project, hash_id):
    time_ms = int(datetime.datetime.now().timestamp() * 1000)
    project_id = str(uuid.uuid4())
    object_of_project = {"owner": email, "projectId": project_id, "createdAt": time_ms, "reportsCount": 0,
                         "likesCount": 0,
                         "viewsCount": 0, "favoritesCount": 0, "commentsCount": 0, "isCommentsDisabled": False,
                         "isDatasetContributor": False,
                         "isEmpty": (False if len(set_of_each_project[hash_id]["assets"]) >= 1 else True),
                         "isLoginRequired": False,
                         "isMatureContent": set_of_each_project[hash_id]["adult_content"], "isMultipleFiles": False,
                         "isPublished": set_of_each_project[hash_id]['visible'],
                         'projectDescription': set_of_each_project[hash_id]['description'],
                         'projectFiles': add_files(hash_id, owner_id, email, set_of_each_project),
                         'projectSoftwares': set_of_each_project[hash_id]['software_items'],
                         'projectSubject1': None, 'projectSubject2': None, 'projectSubject3': None,
                         'projectTags': set_of_each_project[hash_id]['tags'],
                         'projectTitle': title, 'updatedAt': time_ms, 'ownerId': owner_id,
                         'previewImage': obj_of_uploaded_file_to_append}
    return object_of_project


def upload_image_to_imagekit(image_name, image_url):
    public_key = os.getenv('NEXT_PUBLIC_IMAGEKIT_PUBLIC_KEY')
    private_key = os.getenv('IMAGEKIT_PRIVATE_KEY')
    url_endpoint = os.getenv('NEXT_PUBLIC_IMAGEKIT_URL_ENDPOINT')
    imagekit = ImageKit(
        public_key=public_key,
        private_key=private_key,
        url_endpoint=url_endpoint
    )

    upload = imagekit.upload(
        file=image_url,
        file_name=image_name,
        options=UploadFileRequestOptions(),
    )

    # print("Upload url", upload)
    #
    # # Raw Response
    # print(upload.response_metadata.raw)
    #
    # # print that uploaded file's ID
    # print(upload.file_id)
    return upload.response_metadata.raw


@app.route('/upload_software_icons', methods=[
    'POST'])  # fetch software icons of art station to us and upload it in cloudinary and get back all the links
def upload_icons_to_cloudinary():  # fetch_all_artstation_software_icons_and_upload_to_our_cloud with the return of all the new id's that were generated
    urls = []
    letters = "a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,tu,v,w,x,y,z".split(',')

    for i in letters:
        for j in letters:
            urls.append('https://www.artstation.com/autocomplete/software.json?q=' + i + j)
    requestss = (grequests.get(u) for u in urls)
    responses = grequests.map(requestss)
    json_data = [response.json() for response in responses]
    counter_id = 0
    ready_list = []
    list_ids = []
    api = "https://api.imgur.com/3/image"
    replicated_list = list(filter(lambda x: x, json_data))
    for obj_list in replicated_list:
        for obj in obj_list:
            if obj['id'] not in list_ids:
                ready_list.append(obj)
                list_ids.append(obj['id'])
                obj['artstation_id'] = obj['id']
                # downloading each image
                image_url_small = obj['icon_default_url']
                image_url_big = obj['icon_url']
                image_small_name = image_url_small.rsplit('/', 1)[1]
                image_small_name = image_small_name.split('.')[0]
                print(image_small_name)
                image_big_name = image_url_big.rsplit('/', 1)[1]
                image_big_name = image_big_name.split('.')[0]
                cloudinary.uploader.upload(image_url_small, public_id=image_small_name + "_default",
                                           unique_filename=False, overwrite=True)
                # Build the URL for the image and save it in the variable 'srcURL'
                srcURL = cloudinary.CloudinaryImage(image_small_name + "_default").build_url()
                obj["icon_default_url"] = srcURL
                cloudinary.uploader.upload(image_url_big, public_id=image_big_name + "_big", unique_filename=False,
                                           overwrite=True)
                # Build the URL for the image and save it in the variable 'srcURL'
                srcURL = cloudinary.CloudinaryImage(image_big_name + "_big").build_url()
                obj["icon_url"] = srcURL
    for obj in ready_list:
        obj['id'] = counter_id
        counter_id += 1
    return ready_list


@app.route('/scrape_discord', methods=['POST'])  # input channel_id , channel_name ,
def scrape_discord():  # fetch_all_artstation_software_icons_and_upload_to_our_cloud with the return of all the new id's that were generated
    data = request.json
    header = {'authorization': data['authorization']}
    all_midjourney_motherfucking_images = []
    # for channel in all_channels:
    #     send_request_to = 'https://discord.com/api/v9/channels/' + channel + '/messages'
    #     r = requests.get(send_request_to, headers=header)
    #     jsonn = json.loads(r.text)
    #     for value in jsonn:
    #         print(value)
    #         for pictures in value['attachments']:
    #             all_midjourney_motherfucking_images.append(pictures['url'])
    #             all_midjourney_motherfucking_images.append(pictures['proxy_url'])
    #     return all_midjourney_motherfucking_images
    # print(all_midjourney_motherfucking_images)

    CHANNELID = data['channel']
    LIMIT = 100
    channel_name = data['channel_name']
    filename = CHANNELID + '_' + channel_name + '.txt'
    if not os.path.exists(filename):
        open(filename, 'w').close()
        print('File created')
    with open(filename, 'r') as f:
        text = f.read()
        lines = text.split('\n')
        set_of_links = set(lines)
    r = requests.get(f'https://discord.com/api/v9/channels/{CHANNELID}/messages?limit={LIMIT}', headers=header)
    jsonn = json.loads(r.text)
    put_in_file(jsonn, CHANNELID, channel_name, set_of_links)
    task_it(r, LIMIT, CHANNELID, header, channel_name, set_of_links)
    return 'finished'


def task_it(r, LIMIT, CHANNELID, header, channel_name, set_of_links):
    # flag = True
    while len(r.json()) == LIMIT:  # and flag is True:
        last_message_id = r.json()[-1].get('id')
        r = requests.get(
            f'https://discord.com/api/v9/channels/{CHANNELID}/messages?limit={LIMIT}&before={last_message_id}',
            headers=header)
        jsonn = json.loads(r.text)
        put_in_file(jsonn, CHANNELID, channel_name, set_of_links)


def put_in_file(jsonn, CHANNELID, channel_name, set_of_links):
    for value in jsonn:
        for pictures in value['attachments']:
            with open(CHANNELID + '_' + channel_name + '.txt', 'a') as f:
                if pictures['url'] in set_of_links:
                    return
                if pictures['url'] is not None:
                    set_of_links.add(pictures['url'])
                    f.write(pictures['url'] + '\n')
                if pictures['proxy_url'] in set_of_links:
                    return
                if pictures['proxy_url'] is not None:
                    set_of_links.add(pictures['proxy_url'])
                    f.write(pictures['proxy_url'] + '\n')


# todo
# https://www.artstation.com/?sort_by=community - retrieve
@app.route('/collect_users_of_artstation', methods=[
    'POST'])
def the_process():
    data = request.json
    file_text_to_store_name = data['file_text_to_store_name']
    counts_per_page = data['counts_per_page']
    set_of_users = collect_users_of_artstation(counts_per_page, file_text_to_store_name)
    with open(file_text_to_store_name + '.txt', 'w') as f:
        for item in set_of_users:
            f.write(item + '\n')
    return "hi"


# this function will gather all the users of art_station
def collect_users_of_artstation(counts_per_page, file_text_to_store_name):
    set_of_users = set()
    page_number = 1
    if not os.path.exists(file_text_to_store_name + '.txt'):
        open(file_text_to_store_name + '.txt', 'w').close()
        print('File created')
    else:
        with open(file_text_to_store_name + '.txt', 'r') as f:
            text = f.read()
            lines = text.split('\n')
            set_of_users = set(lines)
    r = requests.get(
        f'https://www.artstation.com/api/v2/community/explore/projects/community.json?page={page_number}&dimension=all&per_page={counts_per_page}')
    pre_len_set_of_users = None
    while r.json() is not None and len(r.json()['data']) == counts_per_page and pre_len_set_of_users != len(
            set_of_users):
        jsonn = json.loads(r.text)
        all_data = jsonn['data']
        pre_len_set_of_users = len(set_of_users)
        for user in all_data:
            set_of_users.add(user['user']['username'])
        page_number += 1
        r = requests.get(
            f'https://www.artstation.com/api/v2/community/explore/projects/community.json?page={page_number}&dimension=all&per_page={counts_per_page}')
        print(len(set_of_users))
    return set_of_users


@app.route('/send_messages', methods=['POST'])
def send_messages():
    data = request.json
    file_text_name = data['file_text_name']
    # email = data['email']
    # password = data['password']
    # driver = webdriver.Chrome()
    driver = uc.Chrome(use_subprocess=True)
    print("You're in!! enjoy")
    set_of_users = None
    with open(file_text_name + '.txt', 'r') as f:
        text = f.read()
        lines = text.split('\n')
        set_of_users = set(lines)
    # browser.get("https://www.artstation.com/users/sign_in")
    # input[type = email]
    # email_field = driver.find_element(By.XPATH, '//*[@id="user_email"]')
    # password_field = driver.find_element(By.XPATH, '//*[@id="user_password"]')
    # email_field.send_keys(email)
    # password_field.send_keys(password)
    # sign_in_btn = browser.find_element(By.XPATH, "//*[@id='new_user']/div[5]/button")
    # time.sleep(65)
    # driver.implicitly_wait(15) # a good tool to wait if something is not presented in the dom
    for specific_user in set_of_users:
        print(specific_user)
        current_link = "https://www.artstation.com/" + str(specific_user)
        driver.get(current_link)
        time.sleep(5)
        # e = driver.find_element(By.XPATH, '//button[normalize-space()="Message"]')
        # e.click()
        # time.sleep(5)
        # buttons = driver.find_elements('btn')
        # print(buttons)


if __name__ == '__main__':
    app.run(host='localhost', port=5000)
