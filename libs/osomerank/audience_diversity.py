#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Apr 13 16:06:26 2024

@author: Saumya, modified by Bao

Functions to calculate the audience diversity of a single or a list of posts. The model is trained on the audience diversity of the URLs in the NewsGuard dataset.
Inputs: 
    - 
"""

from bertopic import BERTopic
import pandas as pd
import re
import requests
import json
import traceback
from osomerank.unshorten_URLs import unshorten_main

import os
import configparser

AD_MEAN = 4.86
AD_STD = 1.64
TD_MEAN = 2.66
TD_STD = 1.77
mean_topic_diversity = 0

platform_urls = [
        'twitter.com',
        'youtube.com',
        'youtu.be',
        'pubmed.ncbi.nlm.nih.gov',
        'ncbi.nlm.nih.gov',
        'tumblr.com',
        'wikipedia.org',
        'reddit.com',
        'facebook.com',
        'medium.com',
        'pbs.twimg'
    ]

libs_path = os.path.dirname(__file__)
config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), "config.ini"))

# Need to remove domains whih are platform corref from NewsGuard data
pd_audience_diversity_URLs = pd.read_csv(
    os.path.join(libs_path, config.get("AUDIENCE_DIVERSITY", "audience_diversity_file"))
)
pd_audience_diversity_URLs = pd_audience_diversity_URLs.loc[
    pd_audience_diversity_URLs["n_visitors"] >= 10
]
audience_diversity_domains = (
    pd_audience_diversity_URLs["private_domain"].unique().tolist()
)

BERTopic_model_loaded = BERTopic.load(
    os.path.join(
        libs_path, config.get("AUDIENCE_DIVERSITY", "audience_diversity_BERTtopic")
    )
)
# BERTopic_model_loaded = BERTopic.load()

topic_diversity = {}
with open(
    os.path.join(libs_path, config.get("AUDIENCE_DIVERSITY", "topic_diversity_json"))
) as ff:
    topic_diversity = json.load(ff)


def URL_from_text(myString):
    if not re.search("(?P<url>https?://[^\s]+)", myString):
        return "NA"
    return re.search("(?P<url>https?://[^\s]+)", myString).group("url")


def process_URL(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        return r.url
    except Exception:
        return url


def process_URL_multiple(urls):
    res = []
    for url in urls:
        try:
            r = requests.head(url, allow_redirects=True, timeout=10)
            res.append(r.url)
        except Exception:
            res.append(url)
    return res


def remove_urls(text, replacement_text=""):
    # Define a regex pattern to match URLs
    url_pattern = re.compile(r"https?://\S+|www\.\S+")

    # Use the sub() method to replace URLs with the specified replacement text
    text_without_urls = url_pattern.sub(replacement_text, text)

    return text_without_urls


# Filtering text: remove special characters, alphanumeric, return None if text doesn't meet some criterial like just one word or something
def process_text(text):
    text_urls_removed = remove_urls(text)
    if len(text.strip().split(" ")) <= 3:
        return "NA"
    return text_urls_removed


# Filtering text: remove special characters, alphanumeric, return None if text doesn't meet some criterial like just one word or something
def process_text_multiple(texts):
    processed_texts = []
    for text in texts:
        text_urls_removed = remove_urls(text)
        if len(text_urls_removed.strip().split(" ")) <= 3:
            processed_texts.append("NA")
        else:
            processed_texts.append(text_urls_removed)
    return processed_texts


def ad_prediction(feed_posts, sm_type):
    urls_available = []
    urls_index = []

    audience_diversity_val = [-1000] * len(feed_posts)

    try:
        if sm_type == "twitter":
            for i in range(len(feed_posts)):
                feed_post = feed_posts[i]
                if feed_post["embedded_urls"]:
                    for urll in feed_post["embedded_urls"]:
                        if not any([platform_url in urll for platform_url in platform_urls]):
                            urls_index.append(i)
                            urls_available.append(urll)

        else:
            for i in range(len(feed_posts)):
                feed_post = feed_posts[i]
                if "text" in feed_post.keys():
                    if type(feed_post["text"]) != float:
                        url_from_text = URL_from_text(feed_post["text"])
                        if url_from_text != "NA":
                            if not any([platform_url in url_from_text for platform_url in platform_urls]):
                                urls_index.append(i)
                                urls_available.append(url_from_text)

        if urls_available:
            urls_available_unshortened = unshorten_main(urls_available)
            # urls_available_unshortened = process_URL_multiple(urls_available)
        else:
            urls_available_unshortened = []

        for i in range(len(urls_available_unshortened)):
            url_available = urls_available_unshortened[i]
            domain = ".".join(url_available.split("/")[2].split(".")[-2:])
            if domain in audience_diversity_domains:
                if not any([platform_url in domain for platform_url in platform_urls]):
                    ad_val = pd_audience_diversity_URLs.loc[
                        pd_audience_diversity_URLs["private_domain"] == domain
                    ]["visitor_var"].values[0]
                    audience_diversity_val[urls_index[i]] = (ad_val - AD_MEAN)/AD_STD

        sm_texts = []
        text_index = []

        for i in range(len(feed_posts)):
            if audience_diversity_val[i] == -1000:
                feed_post = feed_posts[i]
                if sm_type == "reddit":
                    if "title" in feed_post.keys() and "text" in feed_post.keys():
                        sm_texts.append(feed_post["title"] + ". " + feed_post["text"])
                        text_index.append(i)
                    elif "title" in feed_post.keys():
                        sm_texts.append(feed_post["title"])
                        text_index.append(i)
                    elif "text" in feed_post.keys():
                        sm_texts.append(feed_post["text"])
                        text_index.append(i)
                else:
                    if type(feed_post["text"]) != float:
                        sm_texts.append(feed_post["text"])
                        text_index.append(i)

        sm_texts_processed = process_text_multiple(sm_texts)
        texts_processed = []
        text_index_processed = []

        for i in range(len(sm_texts_processed)):
            if sm_texts_processed[i] != "NA":
                texts_processed.append(sm_texts_processed[i])
                text_index_processed.append(text_index[i])

        topics = BERTopic_model_loaded.transform(texts_processed)[0]

        for i in range(len(topics)):
            if int(topics[i]) != -1:
                td_val = topic_diversity[
                    str(topics[i])
                ]
                audience_diversity_val[text_index_processed[i]] = (td_val - TD_MEAN)/TD_STD

    except Exception:
        print(traceback.format_exc())
        return mean_topic_diversity

    for i in range(len(audience_diversity_val)):
        if audience_diversity_val[i] == -1000:
            audience_diversity_val[i] = mean_topic_diversity

    return audience_diversity_val

def ad_prediction_single(feed_post, sm_type):
    url_available = ""

    audience_diversity_val = -1000

    try:
        if sm_type == "twitter":
            if feed_post["expanded_url"]:
                url_available = feed_post["expanded_url"]

        else:
            if URL_from_text(feed_post["text"]) != "NA":
                url_available = URL_from_text(feed_post["text"])

        if url_available:
            # url_available = process_URL(url_available)
            domain = ".".join(url_available.split("/")[2].split(".")[-2:])
            if domain in audience_diversity_domains:
                audience_diversity_val = pd_audience_diversity_URLs.loc[
                    pd_audience_diversity_URLs["private_domain"] == domain
                ]["visitor_var"].values[0]

        if audience_diversity_val == -1000:
            sm_text = ""
            if sm_type == "reddit":
                if "title" in feed_post.keys() and "text" in feed_post.keys():
                    sm_text = feed_post["title"] + ". " + feed_post["text"]
                elif "title" in feed_post.keys():
                    sm_text = feed_post["title"]
                else:
                    sm_text = feed_post["text"]
            else:
                sm_text = feed_post["text"]
            if process_text(sm_text) != "NA":
                sm_text = process_text(sm_text)
                topic = BERTopic_model_loaded.transform([sm_text])[0][0]
                if int(topic) != -1:
                    audience_diversity_val = topic_diversity[str(topic)]
    except Exception as e:
        print(e)
        return mean_topic_diversity

    if audience_diversity_val == -1000:
        audience_diversity_val = mean_topic_diversity

    return audience_diversity_val
