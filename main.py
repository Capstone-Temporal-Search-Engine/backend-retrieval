from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from utils.helper import *
from utils.retrieve_utils import *
import logging
import spacy

nlp = spacy.load("en_core_web_sm")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)


@app.route('/retrieve', methods=['POST'])
def retrieve():
    # Get form data
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    query_term = request.form.get('query_term')

    # Validate input
    if not start_time or not end_time or not query_term:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    try:
        start_time = int(start_time)
        end_time = int(end_time)
    except ValueError:
        return jsonify({'error': 'Invalid timestamp format'}), 400
    
    if start_time >= end_time:
        return jsonify({'error': 'start_time must be less than end_time'}), 400
    
    doc = nlp(query_term)
    filtered_query_term = [token.text.lower() for token in doc if not token.is_stop and not token.is_punct]
    
    results = {
        'start_time': start_time,
        'end_time': end_time,
        'filtered_query_term': filtered_query_term
    }

    base_s3_url = "https://tp-search-s3-bucket.s3.us-east-2.amazonaws.com/html_files"
    months = get_months_between(start_time, end_time)
    tokens = filtered_query_term
    index_files_base_path = os.path.abspath('index_files')
    acc = {}
    for month in months:
        dict_file_path =  f'{index_files_base_path}/{month}/dict.txt'
        post_file_path =  f'{index_files_base_path}/{month}/post.txt'
        map_file_path =  f'{index_files_base_path}/{month}/map_s3_name.txt'

        for token in tokens:
            result_term, num_docs, posting_start_idx = retrieve_dict_record(dict_file_path, 65, token)
            if result_term == '-1': continue
            postings = retrieve_postings_record(post_file_path, 20, posting_start_idx, num_docs)
            for posting in postings:
                map_record = retrieve_map_record(map_file_path, 64, posting[1])
                url = f'{base_s3_url}/{month}/{map_record[0]}'
                acc[url] = acc.get(url, 0) + int(posting[0])

    acc = [[tf_idf, url] for url, tf_idf in acc.items()]
    results["results"] = acc
    return jsonify(results)


if __name__ == '__main__':
    app.run(debug=True)

