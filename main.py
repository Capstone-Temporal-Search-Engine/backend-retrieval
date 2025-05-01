from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from utils.helper import *
from utils.retrieve_utils import *
import logging
from utils.dynamo_db_utils import retrieve_metadata_from_dynamo_db

from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

BANNED_PREFIXES = set()
try:
    with open('banned/banned_prefix.txt', 'r') as f:
        BANNED_PREFIXES = set(line.strip() for line in f if line.strip())
    logger.info("Banned prefixes loaded successfully.")
    print(BANNED_PREFIXES)
except FileNotFoundError:
    logger.warning("banned/banned_prefix.txt not found. No prefixes loaded.")
except Exception as e:
    logger.error(f"Error loading banned prefixes: {str(e)}", exc_info=True)


def is_url_banned(url):
    """Check if a URL partially matches any banned prefix."""
    return any(url.startswith(prefix) for prefix in BANNED_PREFIXES)


@app.route('/retrieve', methods=['POST'])
def retrieve():
    # Get form data
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    query_term = request.form.get('query_term')
    query_term = query_term.lower()
    base_s3_url = "https://tp-search-s3-bucket.s3.us-east-2.amazonaws.com"
    
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
    
    results = {
        'start_time': start_time,
        'end_time': end_time,
        'query_term': query_term
    }

    months = get_months_between(start_time, end_time)
    tokens = query_term.split()
    index_files_base_path = os.path.abspath('index_files')
    acc = {}
    
    # First pass: Calculate tf-idf scores
    for month in months:
        dict_file_path =  f'{index_files_base_path}/{month}/dict.txt'
        post_file_path =  f'{index_files_base_path}/{month}/post.txt'
        map_file_path =  f'{index_files_base_path}/{month}/map.txt'
        for token in tokens:
            result_term, num_docs, posting_start_idx = retrieve_dict_record(dict_file_path, 65, token)
            if result_term == '-1': continue
            postings = retrieve_postings_record(post_file_path, 20, posting_start_idx, num_docs)

            with ThreadPoolExecutor() as executor:
                futures = [executor.submit(retrieve_map_record, map_file_path, 37, posting[1]) for posting in postings]
                map_records = [future.result() for future in futures]

            for i, posting in enumerate(postings):
                file_id = map_records[i]
                acc[file_id] = acc.get(file_id, 0) + int(posting[0])

    # Sort by tf-idf and get top 10 entries
    sorted_entries = sorted(acc.items(), key=lambda x: x[1], reverse=True)
    top_10_entries = sorted_entries[:10]
    
    # Only get metadata for top 10 entries
    final_results = []
    with ThreadPoolExecutor() as executor:
        metadata_futures = [executor.submit(retrieve_metadata_from_dynamo_db, file_id) 
                          for file_id, _ in top_10_entries]
        
        for (file_id, tf_idf), future in zip(top_10_entries, metadata_futures):
            metadata = future.result()
            if not is_url_banned(metadata["url"]):
                metadata['s3_url'] = base_s3_url + '/' + metadata['s3_url']
                metadata['tf_idf'] = tf_idf
                final_results.append(metadata)

    results["data"] = final_results
    return jsonify(results)

@app.route('/health', methods=['GET'])
def health_check():
    return 'OK', 200

if __name__ == '__main__':
    app.run(debug=True)