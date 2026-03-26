#!/usr/bin/env python
# coding: utf-8

# In[1]:


get_ipython().system('pip install -U googlemaps pandas')


# In[2]:


import googlemaps
import pandas as pd
import time
import os


# In[3]:


API_KEY = 'Key in your API' 
gmaps = googlemaps.Client(key=API_KEY)


# In[4]:


def run_local_crawl(input_file='ListofGovernmentMarketsHawkerCentres.csv'):
    
    # Load government data
    df_centres = pd.read_csv(input_file)
    all_reviews = []
    
    print(f"Starting crawl for {len(df_centres)} centres...")

    for index, row in df_centres.iterrows():
        centre_name = row['name_of_centre']
        address = row['location_of_centre']
        
        print(f"📍 Mapping: {centre_name}")

        # Convert address to coordinates [cite: 45]
        geocode_result = gmaps.geocode(address)
        if not geocode_result: continue
            
        lat = geocode_result[0]['geometry']['location']['lat']
        lng = geocode_result[0]['geometry']['location']['lng']

        # Find individual stalls (type='restaurant') within 30m [cite: 6, 45]
        stalls = gmaps.places_nearby(location=(lat, lng), radius=30, type='restaurant')

        for stall in stalls.get('results', []):
            stall_name = stall['name']
            place_id = stall['place_id']
            
            # Pull the actual reviews [cite: 26, 45]
            details = gmaps.place(place_id=place_id, fields=['name', 'review'])
            reviews = details.get('result', {}).get('reviews', [])

            for r in reviews:
                all_reviews.append({
                    "hawker_centre": centre_name,
                    "stall_name": stall_name,
                    "review_text": r.get('text'),
                    "rating": r.get('rating'),
                    "timestamp": r.get('time')
                })
        
        time.sleep(0.2) # Avoid hitting limits [cite: 116]

    # Save and remove duplicates as per assignment rules [cite: 30]
    output_df = pd.DataFrame(all_reviews).drop_duplicates(subset=['review_text'])
    output_df.to_csv('hawker_reviews_corpus.csv', index=False)
    
    print(f"✅ Success! Collected {len(output_df)} unique reviews.")

run_local_crawl()


# In[9]:


def run_custom_balanced_crawl(input_file='ListofGovernmentMarketsHawkerCentres.csv'):
    # Load your government data
    df_centres = pd.read_csv(input_file)
    final_corpus = []
    
    print(f"🚀 Starting crawl for {len(df_centres)} centres...")

    for index, row in df_centres.iterrows():
        centre_name = row['name_of_centre']
        address = row['location_of_centre']
        
        # Geocoding to get coordinates [cite: 45]
        geocode_result = gmaps.geocode(address)
        if not geocode_result: continue
        lat = geocode_result[0]['geometry']['location']['lat']
        lng = geocode_result[0]['geometry']['location']['lng']

        # Find stalls within 30m
        stalls = gmaps.places_nearby(location=(lat, lng), radius=30, type='restaurant')

        for stall in stalls.get('results', []):
            place_id = stall['place_id']
            # Get reviews with text and rating [cite: 66]
            details = gmaps.place(place_id=place_id, fields=['name', 'review'])
            reviews = details.get('result', {}).get('reviews', [])

            for r in reviews:
                text = r.get('text', '')
                rating = r.get('rating')
                
                # UPDATED LOGIC: 5 stars = Good, < 3 stars (1 or 2) = Bad 
                if rating == 5 or rating < 3:
                    sentiment_label = "Positive" if rating == 5 else "Negative"
                    final_corpus.append({
                        "hawker_centre": centre_name,
                        "stall_name": stall['name'],
                        "review_text": text,
                        "star_rating": rating,
                        "initial_sentiment": sentiment_label,
                        "word_count": len(text.split()) # 
                    })
        
        time.sleep(0.1) # Safe API pacing

    # 2. SAVE AND EXPORT
    df_output = pd.DataFrame(final_corpus).drop_duplicates(subset=['review_text']) # [cite: 30]
    
    # Save the full corpus [cite: 145]
    df_output.to_csv('hawker_reviews_full.csv', index=False)
    
    # Generate the official eval.xls (1,000 records) [cite: 29, 112]
    eval_subset = df_output.sample(n=min(1000, len(df_output)))
    eval_subset.to_excel('eval.xls', index=False)
    
    total_words = df_output['word_count'].sum()
    print(f"✅ Success! Collected {len(df_output)} unique reviews.")
    print(f"📊 Total word count: {total_words} (Target: 100,000+)") [cite: 27]
    
    return df_output

# Run it!
final_df = run_custom_balanced_crawl()


# In[11]:


def run_final_10k_crawl(input_file='ListofGovernmentMarketsHawkerCentres.csv'):
    df_centres = pd.read_csv(input_file)
    final_corpus = []
    unique_texts = set()
    
    print(f"🚀 Starting crawl for 10,000 records (with Pagination)...")

    for index, row in df_centres.iterrows():
        centre_name = row['name_of_centre']
        address = row['location_of_centre']
        
        # Geocode the address
        geocode_result = gmaps.geocode(address)
        if not geocode_result: continue
        lat, lng = geocode_result[0]['geometry']['location']['lat'], geocode_result[0]['geometry']['location']['lng']

        # --- PAGINATION LOGIC TO BREAK THE 5000 LIMIT ---
        stalls_results = []
        next_page_token = None
        
        # Loop up to 3 times to get all 60 possible stalls per centre
        for _ in range(3):
            if next_page_token:
                response = gmaps.places_nearby(page_token=next_page_token)
            else:
                response = gmaps.places_nearby(location=(lat, lng), radius=50, type='restaurant')
            
            stalls_results.extend(response.get('results', []))
            next_page_token = response.get('next_page_token')
            
            if not next_page_token: break
            time.sleep(2) # Google needs 2 seconds for tokens to activate

        for stall in stalls_results:
            place_id = stall['place_id']
            details = gmaps.place(place_id=place_id, fields=['name', 'review'])
            reviews = details.get('result', {}).get('reviews', [])

            for r in reviews:
                text = r.get('text', '')
                rating = r.get('rating')
                
                if text not in unique_texts and text != '':
                    # Criteria: 5=Good, 3=Mixed, <3=Bad
                    if rating == 5 or rating == 3 or rating < 3:
                        unique_texts.add(text)
                        sentiment = "Positive" if rating == 5 else ("Neutral" if rating == 3 else "Negative")
                        
                        final_corpus.append({
                            "hawker_centre": centre_name,
                            "stall_name": stall['name'],
                            "review_text": text,
                            "star_rating": rating,
                            "sentiment": sentiment,
                            "word_count": len(text.split())
                        })

        if index % 5 == 0:
            print(f"📈 Progress: {len(final_corpus)} reviews collected...")
        
        # Stop if we hit 11,000 (gives us a 1,000 record buffer)
        if len(final_corpus) >= 11000: break

    # 2. SAVE AS XLSX (TO AVOID YOUR ERROR)
    df_output = pd.DataFrame(final_corpus)
    
    # Save the full corpus as CSV (standard for the assignment)
    df_output.to_csv('hawker_corpus_final.csv', index=False)
    
    # Save the evaluation set as XLSX (pandas likes this better)
    eval_subset = df_output.sample(n=min(1000, len(df_output)))
    eval_subset.to_excel('eval.xlsx', index=False) # Changed from .xls to .xlsx
    
    print(f"\n✅ SUCCESS!")
    print(f"📝 Total Unique Records: {len(df_output)}")
    print(f"📊 Total Word Count: {df_output['word_count'].sum()}")
    print(f"📂 Files saved: 'hawker_corpus_final.csv' and 'eval.xlsx'")

# Run it!
run_final_10k_crawl()


# In[15]:


def run_final_10k_crawl(input_file='ListofGovernmentMarketsHawkerCentres.csv'):
    df_centres = pd.read_csv(input_file)
    final_corpus = []
    unique_texts = set()
    
    print(f"🚀 Starting crawl for 10,000 records (Chinese Language Support)...")

    for index, row in df_centres.iterrows():
        centre_name = row['name_of_centre']
        address = row['location_of_centre']
        
        geocode_result = gmaps.geocode(address)
        if not geocode_result: continue
        lat, lng = geocode_result[0]['geometry']['location']['lat'], geocode_result[0]['geometry']['location']['lng']

        # Pagination for the 10k goal
        stalls_results = []
        next_page_token = None
        for _ in range(3):
            if next_page_token:
                response = gmaps.places_nearby(page_token=next_page_token)
            else:
                response = gmaps.places_nearby(location=(lat, lng), radius=50, type='restaurant')
            
            stalls_results.extend(response.get('results', []))
            next_page_token = response.get('next_page_token')
            if not next_page_token: break
            time.sleep(2) 

        for stall in stalls_results:
            place_id = stall['place_id']
            # We don't filter by language so we get both English and Chinese reviews
            details = gmaps.place(place_id=place_id, fields=['name', 'review'])
            reviews = details.get('result', {}).get('reviews', [])

            for r in reviews:
                text = r.get('text', '')
                rating = r.get('rating')
                
                if text not in unique_texts and text != '':
                    if rating == 5 or rating == 3 or rating < 3:
                        unique_texts.add(text)
                        sentiment = "Positive" if rating == 5 else ("Neutral" if rating == 3 else "Negative")
                        
                        final_corpus.append({
                            "hawker_centre": centre_name,
                            "stall_name": stall['name'],
                            "review_text": text,
                            "star_rating": rating,
                            "sentiment": sentiment,
                            "word_count": len(text.split())
                        })

        if index % 5 == 0:
            print(f"📈 Progress: {len(final_corpus)} reviews collected...")
        if len(final_corpus) >= 11000: break

    # --- THE CRITICAL FIX FOR CHINESE CHARACTERS ---
    df_output = pd.DataFrame(final_corpus)
    
    # encoding='utf-8-sig' ensures Excel shows Chinese characters correctly
    df_output.to_csv('hawker_corpus_final10k.csv', index=False, encoding='utf-8-sig')
    
    # Excel .xlsx files handle Chinese characters natively
    eval_subset = df_output.sample(n=min(1000, len(df_output)))
    eval_subset.to_excel('eval.xlsx', index=False) 
    
    print(f"\n✅ SUCCESS!")
    print(f"📝 Total Unique Records: {len(df_output)}")
    print(f"📂 Files saved with Chinese support: 'hawker_corpus_final.csv' and 'eval.xlsx'")

# Run it!
run_final_10k_crawl()


# In[ ]:




