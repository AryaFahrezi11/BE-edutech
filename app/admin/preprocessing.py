import re
from collections import Counter
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory

# Inisialisasi Sastrawi
stemmer_factory = StemmerFactory()
stemmer = stemmer_factory.create_stemmer()

stopword_factory = StopWordRemoverFactory()
stopword_remover = stopword_factory.create_stop_word_remover()

def clean_text(text):
    """
    Membersihkan teks dari karakter non-alfabet dan mengubah ke huruf kecil.
    """
    text = str(text).lower()
    text = re.sub(r'[^a-z\s]', '', text)
    return text.strip()

def preprocess_reviews(reviews):
    """
    Memproses daftar ulasan untuk mendapatkan statistik, distribusi rating, dan top keywords.
    """
    total_reviews = len(reviews)
    if total_reviews == 0:
        return {
            "stats": {"total_reviews": 0, "average_rating": 0},
            "rating_distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            "top_keywords": []
        }

    rating_dist = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    total_score = 0
    all_words = []

    for review in reviews:
        score = review.get("score", 0)
        content = review.get("content", "")

        # Rating distribution
        if str(score) in rating_dist:
            rating_dist[str(score)] += 1
        total_score += score

        # Keyword extraction
        cleaned = clean_text(content)
        if cleaned:
            # Stopword removal
            no_stopword = stopword_remover.remove(cleaned)
            # Stemming
            stemmed = stemmer.stem(no_stopword)
            words = stemmed.split()
            # Hanya ambil kata yang panjangnya > 2
            valid_words = [w for w in words if len(w) > 2]
            all_words.extend(valid_words)

    average_rating = round(total_score / total_reviews, 2)
    
    word_counts = Counter(all_words)
    # Format untuk WordCloud frontend: [{"text": "kata", "weight": jumlah}]
    top_keywords = [{"text": word, "weight": count} for word, count in word_counts.most_common(50)]

    return {
        "stats": {
            "total_reviews": total_reviews,
            "average_rating": average_rating
        },
        "rating_distribution": rating_dist,
        "top_keywords": top_keywords
    }
