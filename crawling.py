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




