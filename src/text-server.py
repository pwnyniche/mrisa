import argparse
import json
import pycurl
import re
from flask import Flask, url_for, jsonify, request
from flask_cors import CORS, cross_origin
python3 = True
import io as bytesIOModule
from bs4 import BeautifulSoup
if python3:
    import certifi
from googlecloudapi import getCloudAPIDetails, saveImage

SEARCH_URL = 'https://www.google.com/search?tbm=isch&hl=en&ijn=0&q='

app = Flask(__name__)


@app.route('/search-text', methods = ['POST'])
def search():
    if request.headers['Content-Type'] != 'application/json':
        return "Requests must be in JSON format. Please make sure the header is 'application/json' and the JSON is valid."
    client_json = json.dumps(request.json)
    client_data = json.loads(client_json)

    if 'cloud_api' in client_data and client_data['cloud_api'] == True:
        saveImage(client_data['text_query'])
        data = getCloudAPIDetails("./default.jpg")
        return jsonify(data)

    else:
        code = doImageSearch(SEARCH_URL + client_data['text_query'])

        if 'resized_images' in client_data and client_data['resized_images'] == True:
            return parseResults(code, resized=True)
        else:
            return parseResults(code)

def doImageSearch(full_url):
    # Directly passing full_url
    """Return the HTML page response."""

    returned_code = bytesIOModule.BytesIO()
    # full_url = SEARCH_URL + text_query

    print(returned_code)

    if app.debug:
        print('POST: ' + full_url)

    conn = pycurl.Curl()
    conn.setopt(conn.CAINFO, certifi.where())
    conn.setopt(conn.URL, str(full_url))
    conn.setopt(conn.FOLLOWLOCATION, 1)
    conn.setopt(conn.USERAGENT, 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:61.0) Gecko/20100101 Firefox/61.0')
    conn.setopt(conn.WRITEFUNCTION, returned_code.write)
    conn.setopt(conn.WRITEDATA, returned_code)
    conn.perform()
    conn.close()
    return returned_code.getvalue().decode('UTF-8')

def parseResults(code, resized=False):
    """Parse/Scrape the HTML code for the info we want."""
    
    soup = BeautifulSoup(code, 'html.parser')
    with open("result.txt", "w") as o:
        o.write(code)
    results = {
        'links': [],
    }

    # this steps could be refactored to a more compact
    all_script_tags = soup.select('script')

    # # https://regex101.com/r/48UZhY/4
    matched_images_data = ''.join(re.findall(r"AF_initDataCallback\(([^<]+)\);", str(all_script_tags)))
    
    # https://kodlogs.com/34776/json-decoder-jsondecodeerror-expecting-property-name-enclosed-in-double-quotes
    # if you try to json.loads() without json.dumps() it will throw an error:
    # "Expecting property name enclosed in double quotes"
    matched_images_data_fix = json.dumps(matched_images_data)
    matched_images_data_json = json.loads(matched_images_data_fix)

    # https://regex101.com/r/pdZOnW/3
    matched_google_image_data = re.findall(r'\[\"GRID_STATE0\",null,\[\[1,\[0,\".*?\",(.*),\"All\",', matched_images_data_json)

    # https://regex101.com/r/NnRg27/1
    matched_google_images_thumbnails = ', '.join(
        re.findall(r'\[\"(https\:\/\/encrypted-tbn0\.gstatic\.com\/images\?.*?)\",\d+,\d+\]',
                   str(matched_google_image_data))).split(', ')

    for fixed_google_image_thumbnail in matched_google_images_thumbnails:
        # https://stackoverflow.com/a/4004439/15164646 comment by Frédéric Hamidi
        google_image_thumbnail_not_fixed = bytes(fixed_google_image_thumbnail, 'ascii').decode('unicode-escape')
        # after first decoding, Unicode characters are still present. After the second iteration, they were decoded.
        google_image_thumbnail = bytes(google_image_thumbnail_not_fixed, 'ascii').decode('unicode-escape')

    # removing previously matched thumbnails for easier full resolution image matches.
    removed_matched_google_images_thumbnails = re.sub(
        r'\[\"(https\:\/\/encrypted-tbn0\.gstatic\.com\/images\?.*?)\",\d+,\d+\]', '', str(matched_google_image_data))

    # https://regex101.com/r/fXjfb1/4
    # https://stackoverflow.com/a/19821774/15164646
    matched_google_full_resolution_images = re.findall(r"(?:'|,),\[\"(https:|http.*?)\",\d+,\d+\]",
                                                       removed_matched_google_images_thumbnails)


    print('\nFull Resolution Images:')  # in order
    for index, fixed_full_res_image in enumerate(matched_google_full_resolution_images):
        # https://stackoverflow.com/a/4004439/15164646 comment by Frédéric Hamidi
        original_size_img_not_fixed = bytes(fixed_full_res_image, 'ascii').decode('unicode-escape')
        original_size_img = bytes(original_size_img_not_fixed, 'ascii').decode('unicode-escape')
        results['links'].append(original_size_img)


    # for similar_image in soup.findAll('div', attrs={'rg_meta'}):
    #     tmp = json.loads(similar_image.get_text())
    #     img_url = tmp['ou']
    #     results['similar_images'].append(img_url)

    for best_guess in soup.findAll('a', attrs={'class':'fKDtNb'})[2:]:
      results['best_guess'] = best_guess.get_text()

    if resized:
        results['resized_images'] = getDifferentSizes(soup)

    print("Successful search")
    return json.dumps(results)

def getDifferentSizes(soup):
    """
    Takes html code ( souped ) as input

    Returns google's meta info on the different sizes of the same image from different websites

    Returns a list of JSON objects of form

    {
        'rh': 'resource_host',
        'ru': 'resource_url',
        'rid': 'SOME_ID_USED_BY_GOOGLE',
        'ou': 'original_url of image
        'oh': 'orginal_height',
        'ow': 'original_width',
        'ity': 'image type',
        'tu': 'thumbnail_url of image', # Generated by google
        'th': 'thumbnail_height',
        'tw': 'thumbnail_width',
        's': 'summary'
        'itg': 'SOME UNKNOWN TERM',
        'pt': 'pt', # some short description (UNKNOWN TERM)
        'sc': "SOME UNKNOWN TERM",
        'id': 'SOME_ID_USED_BY_GOOGLE',
        'st': 'Site', # UNKOWN TERM
        'rt': 'UNKNOWN TERM',
        'isu': 'resource_host', # (UNKNOWN TERM)
    }

    """

    region = soup.find('div',{"class":"O1id0e"})

    span = region.find('span',{"class":"gl"})

    allsizes = False

    try:

        if span.a.get_text() == "All sizes":
            allsizes = True
        else:
            print("not all sizes")
            print(span)
    except Exception as e:
        print(str(e))
        return [{'error':'500','details':'no_images_found'}]

    if allsizes:
        new_url = "https://google.com" + span.a['href']

    resized_images_page = doImageSearch(new_url)

    new_soup = BeautifulSoup(resized_images_page,"lxml")

    main_div = new_soup.find('div',{"id":"search"})

    rg_meta_divs = main_div.findAll('div',{"class":"rg_meta notranslate"})

    results = []

    for item in rg_meta_divs:
        results.append(json.loads(item.text))
    
    print(results)
    return results

def main():
    parser = argparse.ArgumentParser(description='Meta Reverse Image Search API')
    parser.add_argument('-p', '--port', type=int, default=5000, help='port number')
    parser.add_argument('-d','--debug', action='store_true', help='enable debug mode')
    parser.add_argument('-c','--cors', action='store_true', default=False, help="enable cross-origin requests")
    parser.add_argument('-a', '--host', type=str, default='0.0.0.0', help="sets the address to serve on")
    args = parser.parse_args()

    if args.debug:
        app.debug = True

    if args.cors:
        CORS(app, resources=r'/search/*')
        app.config['CORS_HEADERS'] = 'Content-Type'

        global search
        search = cross_origin(search)
        print(" * Running with CORS enabled")


    app.run(host=args.host, port=args.port)

if __name__ == '__main__':
    main()