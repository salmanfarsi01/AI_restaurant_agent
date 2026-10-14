"""
Prompts for AI Restaurant Agent: bilingual, structured, and production-grade.
Avoids full menu dumps; enforces progressive disclosure and structured slot extraction.
"""

LANGUAGE_DETECTION_PROMPT = """Detect the language of the following user message.
Reply with exactly one word: "en" for English or "bn" for Bangla (Bengali).

Message: {message}
Language:"""

INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for "Dhaka Spice House" restaurant.
Classify the customer's message into exactly ONE of the following intents:

- greeting        : Customer is saying hello, hi, starting the conversation, or asking what we serve
- menu_inquiry    : Customer asks about specific food, prices, ingredients, spice levels, or recommendations
- order_update    : Customer wants to add, change, remove, or order food dishes and quantities
- provide_info    : Customer is giving their personal details (full name, email, phone number, address)
- checkout_review : Customer asks to review their cart, finalize, or place the order
- general         : Small talk, gratitude, store policy, hours, or general questions

Reply with ONLY the intent name (one word).

Customer message: {message}
Intent:"""

PROGRESSIVE_GREETING_EN = """স্বাগতম! Welcome to Dhaka Spice House! 🍛
We serve authentic Old Dhaka Biryanis, sizzling Kebabs, Naga Wings, and refreshing Desserts & Drinks.

Here are our top categories:
• 🍛 **Biryani & Mains** (Kachchi Biryani, Chicken Biryani, Beef Tehari)
• 🍢 **Kebabs & Grills** (Chicken Tikka, Beef Sheekh)
• 🍗 **Wings & Appetizers** (Crispy Naga Wings, Honey Garlic Wings)
• 🥤 **Drinks** (Special Borhani, Mango Lassi)
• 🍮 **Desserts** (Shahi Firni, Gulab Jamun)

Would you like a recommendation, or would you like to place an order?
"""

PROGRESSIVE_GREETING_BN = """স্বাগতম! ঢাকা স্পাইস হাউসে আপনাকে স্বাগতম! 🍛
আমরা পরিবেশন করি ঐতিহ্যবাহী পুরান ঢাকার কাচ্চি বিরিয়ানি, শিক কাবাব, ক্রিস্পি উইংস এবং স্পেশাল বোরহানি ও ডেজার্ট।

আমাদের জনপ্রিয় ক্যাটাগরিগুলো:
• 🍛 **বিরিয়ানি ও মেইন ডিশ** (কাচ্চি বিরিয়ানি, চিকেন বিরিয়ানি, বিফ তেহারি)
• 🍢 **কাবাব ও গ্রিল** (চিকেন টিক্কা, বিফ শিক কাবাব)
• 🍗 **উইংস ও স্ন্যাক্স** (ক্রিস্পি নাগা উইংস, হানি গার্লিক উইংস)
• 🥤 **পানীয়** (স্পেশাল বোরহানি, ম্যাঙ্গো লাচ্ছি)
• 🍮 **মিষ্টান্ন** (শাহী ফিরনি, গরম গোলাপ জামুন)

আপনি কি কোনো খাবারের পরামর্শ চান, নাকি সরাসরি অর্ডার করতে চান?
"""

SLOT_EXTRACTION_PROMPT = """You are an information extraction assistant.
Extract customer delivery details from the user's message.
Return strict JSON with these keys:
{{
  "customer_name": string or null,
  "customer_email": string or null,
  "customer_phone": string or null,
  "delivery_address": string or null
}}

If an attribute is not explicitly mentioned, set its value to null.
Only output valid JSON.

Message: {message}
JSON:"""

CART_ACTION_PROMPT = """You are an order item extractor. Given the user message and the available menu context,
extract what the customer wants to add, remove, or modify.
Return strict JSON with this schema:
{{
  "action": "add" | "modify" | "remove" | "clear" | "none",
  "item_name": string,
  "quantity": int
}}

Rules:
1. Match the dish name as closely as possible to the menu context.
2. If the user specifies an item without quantity, default quantity to 1.
3. If no dish or order change is mentioned, set action to "none".
4. Output ONLY valid JSON.

Menu Context:
{context}

User Message: {message}
JSON:"""

RAG_ANSWER_PROMPT_EN = """You are a helpful and polite concierge for "Dhaka Spice House" restaurant.
Answer the customer's question using ONLY the factual context provided below.
If the answer is not in the context, politely say you are not sure and provide our contact number (+880 1700-000000).
Keep the response warm, appetizing, and concise.

Context:
{context}

Question: {question}
Answer:"""

RAG_ANSWER_PROMPT_BN = """আপনি "ঢাকা স্পাইস হাউস" রেস্টুরেন্টের একজন বিনয়ী এবং সহায়ক খাদ্য পরামর্শক।
শুধুমাত্র নিচের প্রদত্ত তথ্যের ভিত্তিতে গ্রাহকের প্রশ্নের উত্তর দিন।
তথ্য না থাকলে বিনীতভাবে বলুন যে আপনি নিশ্চিত নন এবং স্টাফের সাথে যোগাযোগের নম্বর দিন (+৮৮০ ১৭০০-০০০০০০)।
উত্তর সংক্ষিপ্ত, সুস্বাদু এবং বন্ধুত্বপূর্ণ রাখুন।

প্রসঙ্গ:
{context}

প্রশ্ন: {question}
উত্তর:"""
