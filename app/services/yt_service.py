import requests

def get_realtime_adhd_videos(api_key, category):
    """
    Mengambil video dari YouTube secara realtime. 
    Jika API gagal, akan mengembalikan video fallback (cadangan).
    """
    
    # 1. DATA CADANGAN (Fallback) - Muncul jika API Error/Kuota Habis
    fallback_videos = {
        'pengertian-adhd': [
            {'_id': 'z8-m7u_kQ_w', 'title': 'Apa Itu ADHD? - Penjelasan Lengkap', 'description': 'Mengenal kondisi ADHD pada anak.', 'category': 'Pengertian', 'video_url': 'https://www.youtube.com/watch?v=z8-m7u_kQ_w', 'thumbnail': 'https://img.youtube.com/vi/z8-m7u_kQ_w/mqdefault.jpg'},
        ],
        'gejala-adhd': [
            {'_id': '3m9r_v6m7p4', 'title': 'Ciri-ciri ADHD pada Anak Usia Dini', 'description': 'Tanda-tanda yang perlu diwaspadai orang tua.', 'category': 'Gejala', 'video_url': 'https://www.youtube.com/watch?v=3m9r_v6m7p4', 'thumbnail': 'https://img.youtube.com/vi/3m9r_v6m7p4/mqdefault.jpg'},
        ],
        'cara-penanganan': [
            {'_id': 'L0u-kE8B_Y8', 'title': 'Cara Menangani Anak ADHD Tanpa Obat', 'description': 'Terapi perilaku untuk anak ADHD.', 'category': 'Penanganan', 'video_url': 'https://www.youtube.com/watch?v=L0u-kE8B_Y8', 'thumbnail': 'https://img.youtube.com/vi/L0u-kE8B_Y8/mqdefault.jpg'},
        ],
        'tips-parenting': [
            {'_id': 'qWvK2bY_m_Q', 'title': 'Tips Pola Asuh Anak ADHD di Rumah', 'description': 'Sabar menghadapi anak hiperaktif.', 'category': 'Pola Asuh', 'video_url': 'https://www.youtube.com/watch?v=qWvK2bY_m_Q', 'thumbnail': 'https://img.youtube.com/vi/qWvK2bY_m_Q/mqdefault.jpg'},
        ]
    }

    # 2. LOGIKA SEARCH YOUTUBE
    keywords = {
        'pengertian-adhd': 'apa itu ADHD pada anak penjelasan psikolog indonesia',
        'gejala-adhd': 'ciri ciri gejala ADHD anak usia dini dsm-5 indonesia',
        'cara-penanganan': 'cara menangani anak ADHD terapi perilaku indonesia',
        'tips-parenting': 'tips pola asuh anak ADHD indonesia'
    }
    
    search_query = keywords.get(category, 'edukasi ADHD anak indonesia')
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        'part': 'snippet',
        'q': search_query,
        'type': 'video',
        'maxResults': 6,
        'key': api_key,
        'relevanceLanguage': 'id',
        'order': 'relevance'
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if 'error' in data:
            # LIHAT ERROR INI DI TERMINAL FLASK ANDA
            print(f"--- YOUTUBE API ERROR: {data['error']['message']} ---")
            return fallback_videos.get(category, [])

        videos = []
        for item in data.get('items', []):
            video_id = item['id'].get('videoId')
            if not video_id: continue
            
            snippet = item['snippet']
            videos.append({
                '_id': video_id,
                'title': snippet['title'],
                'description': snippet['description'],
                'category': category.replace('-', ' ').title(),
                'video_url': f"https://www.youtube.com/watch?v={video_id}",
                'thumbnail': snippet['thumbnails']['high']['url']
            })
            
        # Jika YouTube memberikan hasil kosong, gunakan fallback
        return videos if videos else fallback_videos.get(category, [])

    except Exception as e:
        print(f"--- KONEKSI GAGAL: {e} ---")
        return fallback_videos.get(category, [])