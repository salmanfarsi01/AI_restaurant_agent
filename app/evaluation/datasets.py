"""
Small bilingual test set for benchmarking. Expand this a lot before running
real experiments -- 15-20 items is a starting skeleton, not a paper-ready set.
"""

TEST_QUERIES = [
    {"lang": "en", "query": "What is the price of Kacchi Biryani?", "expected_contains": ["380"]},
    {"lang": "en", "query": "Do you have any vegetarian dishes?", "expected_contains": ["Khichuri"]},
    {"lang": "en", "query": "What is your cancellation policy?", "expected_contains": ["5 minutes", "20%"]},
    {"lang": "en", "query": "What is the minimum order value?", "expected_contains": ["200"]},
    {"lang": "en", "query": "I want to order 2 chicken tehari", "expected_contains": ["tehari"]},
    {"lang": "bn", "query": "কাচ্চি বিরিয়ানির দাম কত?", "expected_contains": ["৩৮০", "380"]},
    {"lang": "bn", "query": "আপনাদের কোনো নিরামিষ খাবার আছে?", "expected_contains": ["খিচুড়ি"]},
    {"lang": "bn", "query": "বাতিলকরণ নীতি কি?", "expected_contains": ["৫ মিনিট", "২০%"]},
    {"lang": "bn", "query": "সর্বনিম্ন অর্ডার মূল্য কত?", "expected_contains": ["২০০"]},
    {"lang": "bn", "query": "আমি ২টা চিকেন তেহারি অর্ডার করতে চাই", "expected_contains": ["তেহারি"]},
]
