import logging
import os
import re
import random
import time
from pathlib import Path

import pandas as pd
from faker import Faker

# Configure logging: console + file, with level and format
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "data_generation.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Default Faker for name, email, phone (locale-agnostic)
fake = Faker()
# English-only Faker for organization (and for city/state where locale is English)
fake_en = Faker("en_US")

# English Faker locales for names (used 95% of the time for all countries).
# en_IN gives Indian-style English names, en_AU gives Australian-style, etc.
COUNTRY_EN_LOCALES = {
    "India": "en_IN", "Australia": "en_AU", "New Zealand": "en_NZ",
    "Philippines": "en_PH", "Pakistan": "en_PK",
}
# All other countries fall back to en_IN for English names.

# CJK locales: only these are allowed in native script (5% of the time).
CJK_NATIVE_LOCALES = {
    "China": "zh_CN",
    "Japan": "ja_JP",
    "South Korea": "ko_KR",
    "Hong Kong": "zh_TW",
    "Taiwan": "zh_TW",
}
CJK_NATIVE_CHANCE = 0.05  # 5% chance of native-script name for CJK countries

# Faker locales that produce correct phone formats (verified working).
COUNTRY_PHONE_LOCALES = {
    "India": "en_IN",
    "China": "zh_CN",
    "Japan": "ja_JP",
    "South Korea": "ko_KR",
    "Australia": "en_AU",
    "Thailand": "th_TH",
    "Vietnam": "vi_VN",
    "New Zealand": "en_NZ",
    "Nepal": "ne_NP",
    "Indonesia": "id_ID",
}

# For countries where Faker has no valid locale or gives wrong format, use templates.
# '#' is replaced with a random digit at runtime.
COUNTRY_PHONE_TEMPLATES = {
    "Singapore": ["+65 8###-####", "+65 9###-####"],
    "Malaysia": ["+60 1#-### ####", "+60 1#-####-####"],
    "Philippines": ["+63 9##-###-####", "09##-###-####"],
    "Bangladesh": ["+880 1#########", "01#########"],
    "Pakistan": ["+92 3##-#######", "03##-#######"],
    "Sri Lanka": ["+94 7#-###-####", "07#-###-####"],
    "Hong Kong": ["+852 ####-####", "####-####"],
    "Taiwan": ["+886 9##-###-###", "09##-###-###"],
    "Cambodia": ["+855 ##-###-####", "0##-###-####"],
    "Laos": ["+856 20##-###-###"],
    "Myanmar": ["+95 9###-###-###", "09###-###-###"],
    "Mongolia": ["+976 ##-##-####", "##-##-####"],
    "Brunei": ["+673 ###-####"],
}

# Geographically accurate (city, state/province) pairs for every country.
# Faker picks city and state independently, so we must use fixed mappings.
CITIES_STATES = {
    "India": [
        ("Mumbai", "Maharashtra"), ("Pune", "Maharashtra"), ("Nagpur", "Maharashtra"), ("Nashik", "Maharashtra"), ("Aurangabad", "Maharashtra"),
        ("Delhi", "Delhi"), ("New Delhi", "Delhi"),
        ("Bengaluru", "Karnataka"), ("Mysuru", "Karnataka"), ("Mangalore", "Karnataka"), ("Hubli", "Karnataka"),
        ("Hyderabad", "Telangana"), ("Warangal", "Telangana"), ("Karimnagar", "Telangana"),
        ("Chennai", "Tamil Nadu"), ("Coimbatore", "Tamil Nadu"), ("Madurai", "Tamil Nadu"), ("Salem", "Tamil Nadu"), ("Tiruchirappalli", "Tamil Nadu"),
        ("Kolkata", "West Bengal"), ("Howrah", "West Bengal"), ("Siliguri", "West Bengal"), ("Durgapur", "West Bengal"),
        ("Ahmedabad", "Gujarat"), ("Surat", "Gujarat"), ("Vadodara", "Gujarat"), ("Rajkot", "Gujarat"), ("Gandhinagar", "Gujarat"),
        ("Jaipur", "Rajasthan"), ("Jodhpur", "Rajasthan"), ("Udaipur", "Rajasthan"), ("Kota", "Rajasthan"), ("Ajmer", "Rajasthan"),
        ("Lucknow", "Uttar Pradesh"), ("Kanpur", "Uttar Pradesh"), ("Agra", "Uttar Pradesh"), ("Varanasi", "Uttar Pradesh"),
        ("Noida", "Uttar Pradesh"), ("Ghaziabad", "Uttar Pradesh"), ("Meerut", "Uttar Pradesh"), ("Allahabad", "Uttar Pradesh"),
        ("Firozabad", "Uttar Pradesh"), ("Bareilly", "Uttar Pradesh"), ("Aligarh", "Uttar Pradesh"),
        ("Patna", "Bihar"), ("Gaya", "Bihar"), ("Muzaffarpur", "Bihar"), ("Bhagalpur", "Bihar"),
        ("Bhopal", "Madhya Pradesh"), ("Indore", "Madhya Pradesh"), ("Jabalpur", "Madhya Pradesh"), ("Gwalior", "Madhya Pradesh"),
        ("Chandigarh", "Chandigarh"), ("Ludhiana", "Punjab"), ("Amritsar", "Punjab"), ("Jalandhar", "Punjab"),
        ("Dehradun", "Uttarakhand"), ("Haridwar", "Uttarakhand"), ("Rishikesh", "Uttarakhand"),
        ("Bhubaneswar", "Odisha"), ("Cuttack", "Odisha"), ("Rourkela", "Odisha"),
        ("Thiruvananthapuram", "Kerala"), ("Kochi", "Kerala"), ("Kozhikode", "Kerala"), ("Thrissur", "Kerala"),
        ("Guwahati", "Assam"), ("Dibrugarh", "Assam"),
        ("Ranchi", "Jharkhand"), ("Jamshedpur", "Jharkhand"), ("Dhanbad", "Jharkhand"),
        ("Raipur", "Chhattisgarh"), ("Bilaspur", "Chhattisgarh"),
        ("Shimla", "Himachal Pradesh"), ("Dharamshala", "Himachal Pradesh"),
        ("Srinagar", "Jammu and Kashmir"), ("Jammu", "Jammu and Kashmir"),
        ("Panaji", "Goa"), ("Margao", "Goa"),
        ("Gurgaon", "Haryana"), ("Faridabad", "Haryana"), ("Karnal", "Haryana"),
        ("Visakhapatnam", "Andhra Pradesh"), ("Vijayawada", "Andhra Pradesh"), ("Tirupati", "Andhra Pradesh"), ("Guntur", "Andhra Pradesh"),
        ("Imphal", "Manipur"), ("Shillong", "Meghalaya"), ("Aizawl", "Mizoram"),
        ("Kohima", "Nagaland"), ("Gangtok", "Sikkim"), ("Agartala", "Tripura"), ("Itanagar", "Arunachal Pradesh"),
    ],
    "China": [
        ("Beijing", "Beijing"), ("Shanghai", "Shanghai"), ("Guangzhou", "Guangdong"), ("Shenzhen", "Guangdong"), ("Dongguan", "Guangdong"),
        ("Chengdu", "Sichuan"), ("Chongqing", "Chongqing"), ("Hangzhou", "Zhejiang"), ("Ningbo", "Zhejiang"),
        ("Wuhan", "Hubei"), ("Xi'an", "Shaanxi"), ("Nanjing", "Jiangsu"), ("Suzhou", "Jiangsu"), ("Wuxi", "Jiangsu"),
        ("Tianjin", "Tianjin"), ("Qingdao", "Shandong"), ("Jinan", "Shandong"), ("Dalian", "Liaoning"), ("Shenyang", "Liaoning"),
        ("Zhengzhou", "Henan"), ("Changsha", "Hunan"), ("Harbin", "Heilongjiang"), ("Kunming", "Yunnan"),
        ("Fuzhou", "Fujian"), ("Xiamen", "Fujian"), ("Hefei", "Anhui"), ("Nanchang", "Jiangxi"),
    ],
    "Japan": [
        ("Tokyo", "Tokyo"), ("Osaka", "Osaka"), ("Yokohama", "Kanagawa"), ("Kawasaki", "Kanagawa"),
        ("Nagoya", "Aichi"), ("Sapporo", "Hokkaido"), ("Kobe", "Hyogo"), ("Kyoto", "Kyoto"),
        ("Fukuoka", "Fukuoka"), ("Saitama", "Saitama"), ("Hiroshima", "Hiroshima"), ("Sendai", "Miyagi"),
        ("Chiba", "Chiba"), ("Kitakyushu", "Fukuoka"), ("Niigata", "Niigata"), ("Hamamatsu", "Shizuoka"),
        ("Kumamoto", "Kumamoto"), ("Okayama", "Okayama"), ("Shizuoka", "Shizuoka"), ("Kagoshima", "Kagoshima"),
    ],
    "South Korea": [
        ("Seoul", "Seoul"), ("Busan", "Busan"), ("Incheon", "Incheon"), ("Daegu", "Daegu"),
        ("Daejeon", "Daejeon"), ("Gwangju", "Gwangju"), ("Suwon", "Gyeonggi"), ("Ulsan", "Ulsan"),
        ("Seongnam", "Gyeonggi"), ("Goyang", "Gyeonggi"), ("Yongin", "Gyeonggi"), ("Changwon", "South Gyeongsang"),
        ("Cheongju", "North Chungcheong"), ("Jeonju", "North Jeolla"), ("Jeju", "Jeju"),
    ],
    "Australia": [
        ("Sydney", "New South Wales"), ("Melbourne", "Victoria"), ("Brisbane", "Queensland"),
        ("Perth", "Western Australia"), ("Adelaide", "South Australia"), ("Canberra", "Australian Capital Territory"),
        ("Hobart", "Tasmania"), ("Darwin", "Northern Territory"), ("Gold Coast", "Queensland"),
        ("Newcastle", "New South Wales"), ("Wollongong", "New South Wales"), ("Geelong", "Victoria"),
        ("Cairns", "Queensland"), ("Townsville", "Queensland"), ("Toowoomba", "Queensland"),
    ],
    "Singapore": [
        ("Singapore", "Central"), ("Jurong East", "West"), ("Tampines", "East"), ("Woodlands", "North"),
        ("Bedok", "East"), ("Ang Mo Kio", "Central"), ("Toa Payoh", "Central"), ("Bishan", "Central"),
        ("Clementi", "West"), ("Punggol", "North-East"), ("Sengkang", "North-East"), ("Bukit Batok", "West"),
    ],
    "Malaysia": [
        ("Kuala Lumpur", "Kuala Lumpur"), ("George Town", "Penang"), ("Johor Bahru", "Johor"),
        ("Ipoh", "Perak"), ("Shah Alam", "Selangor"), ("Petaling Jaya", "Selangor"), ("Subang Jaya", "Selangor"),
        ("Kuching", "Sarawak"), ("Kota Kinabalu", "Sabah"), ("Melaka", "Melaka"),
        ("Alor Setar", "Kedah"), ("Kuantan", "Pahang"), ("Putrajaya", "Putrajaya"),
    ],
    "Thailand": [
        ("Bangkok", "Bangkok"), ("Chiang Mai", "Chiang Mai"), ("Phuket", "Phuket"), ("Hat Yai", "Songkhla"),
        ("Khon Kaen", "Khon Kaen"), ("Nakhon Ratchasima", "Nakhon Ratchasima"), ("Udon Thani", "Udon Thani"),
        ("Pattaya", "Chonburi"), ("Chiang Rai", "Chiang Rai"), ("Surat Thani", "Surat Thani"),
        ("Nonthaburi", "Nonthaburi"), ("Ubon Ratchathani", "Ubon Ratchathani"),
    ],
    "Philippines": [
        ("Manila", "Metro Manila"), ("Quezon City", "Metro Manila"), ("Makati", "Metro Manila"), ("Pasig", "Metro Manila"),
        ("Cebu City", "Cebu"), ("Davao City", "Davao del Sur"), ("Zamboanga City", "Zamboanga del Sur"),
        ("Iloilo City", "Iloilo"), ("Bacolod", "Negros Occidental"), ("Cagayan de Oro", "Misamis Oriental"),
        ("Baguio", "Benguet"), ("General Santos", "South Cotabato"), ("Taguig", "Metro Manila"),
    ],
    "Vietnam": [
        ("Ho Chi Minh City", "Ho Chi Minh City"), ("Hanoi", "Hanoi"), ("Da Nang", "Da Nang"),
        ("Haiphong", "Haiphong"), ("Can Tho", "Can Tho"), ("Bien Hoa", "Dong Nai"),
        ("Nha Trang", "Khanh Hoa"), ("Hue", "Thua Thien Hue"), ("Vung Tau", "Ba Ria-Vung Tau"),
        ("Buon Ma Thuot", "Dak Lak"), ("Da Lat", "Lam Dong"), ("Vinh", "Nghe An"),
    ],
    "Indonesia": [
        ("Jakarta", "Jakarta"), ("Surabaya", "East Java"), ("Bandung", "West Java"), ("Medan", "North Sumatra"),
        ("Semarang", "Central Java"), ("Makassar", "South Sulawesi"), ("Palembang", "South Sumatra"),
        ("Depok", "West Java"), ("Tangerang", "Banten"), ("Bekasi", "West Java"),
        ("Yogyakarta", "Yogyakarta"), ("Denpasar", "Bali"), ("Malang", "East Java"), ("Balikpapan", "East Kalimantan"),
    ],
    "New Zealand": [
        ("Auckland", "Auckland"), ("Wellington", "Wellington"), ("Christchurch", "Canterbury"),
        ("Hamilton", "Waikato"), ("Tauranga", "Bay of Plenty"), ("Dunedin", "Otago"),
        ("Palmerston North", "Manawatu-Wanganui"), ("Napier", "Hawke's Bay"), ("Nelson", "Nelson"),
        ("Rotorua", "Bay of Plenty"), ("New Plymouth", "Taranaki"), ("Invercargill", "Southland"),
    ],
    "Bangladesh": [
        ("Dhaka", "Dhaka"), ("Chittagong", "Chittagong"), ("Khulna", "Khulna"), ("Rajshahi", "Rajshahi"),
        ("Sylhet", "Sylhet"), ("Rangpur", "Rangpur"), ("Comilla", "Chittagong"), ("Gazipur", "Dhaka"),
        ("Narayanganj", "Dhaka"), ("Mymensingh", "Mymensingh"),
    ],
    "Pakistan": [
        ("Karachi", "Sindh"), ("Lahore", "Punjab"), ("Islamabad", "Islamabad"), ("Rawalpindi", "Punjab"),
        ("Faisalabad", "Punjab"), ("Multan", "Punjab"), ("Peshawar", "Khyber Pakhtunkhwa"),
        ("Quetta", "Balochistan"), ("Sialkot", "Punjab"), ("Hyderabad", "Sindh"),
        ("Gujranwala", "Punjab"), ("Bahawalpur", "Punjab"),
    ],
    "Sri Lanka": [
        ("Colombo", "Western"), ("Kandy", "Central"), ("Galle", "Southern"), ("Jaffna", "Northern"),
        ("Negombo", "Western"), ("Anuradhapura", "North Central"), ("Trincomalee", "Eastern"),
        ("Batticaloa", "Eastern"), ("Matara", "Southern"), ("Kurunegala", "North Western"),
    ],
    "Hong Kong": [
        ("Central", "Hong Kong Island"), ("Wan Chai", "Hong Kong Island"), ("Causeway Bay", "Hong Kong Island"),
        ("Kowloon", "Kowloon"), ("Tsim Sha Tsui", "Kowloon"), ("Mong Kok", "Kowloon"),
        ("Tsuen Wan", "New Territories"), ("Sha Tin", "New Territories"), ("Tuen Mun", "New Territories"),
    ],
    "Taiwan": [
        ("Taipei", "Taipei"), ("Kaohsiung", "Kaohsiung"), ("Taichung", "Taichung"), ("Tainan", "Tainan"),
        ("Taoyuan", "Taoyuan"), ("Keelung", "Keelung"), ("Hsinchu", "Hsinchu"), ("Chiayi", "Chiayi"),
    ],
    "Nepal": [
        ("Kathmandu", "Bagmati"), ("Pokhara", "Gandaki"), ("Lalitpur", "Bagmati"),
        ("Bharatpur", "Bagmati"), ("Biratnagar", "Province No. 1"), ("Birgunj", "Madhesh"),
        ("Dharan", "Province No. 1"), ("Butwal", "Lumbini"),
    ],
    "Cambodia": [
        ("Phnom Penh", "Phnom Penh"), ("Siem Reap", "Siem Reap"), ("Battambang", "Battambang"),
        ("Sihanoukville", "Preah Sihanouk"), ("Kampong Cham", "Kampong Cham"), ("Poipet", "Banteay Meanchey"),
    ],
    "Laos": [
        ("Vientiane", "Vientiane"), ("Luang Prabang", "Luang Prabang"), ("Pakse", "Champasak"),
        ("Savannakhet", "Savannakhet"), ("Thakhek", "Khammouane"),
    ],
    "Myanmar": [
        ("Yangon", "Yangon"), ("Mandalay", "Mandalay"), ("Naypyidaw", "Naypyidaw"),
        ("Mawlamyine", "Mon"), ("Taunggyi", "Shan"), ("Pathein", "Ayeyarwady"),
    ],
    "Mongolia": [
        ("Ulaanbaatar", "Ulaanbaatar"), ("Erdenet", "Orkhon"), ("Darkhan", "Darkhan-Uul"),
        ("Choibalsan", "Dornod"), ("Murun", "Khuvsgul"),
    ],
    "Brunei": [
        ("Bandar Seri Begawan", "Brunei-Muara"), ("Tutong", "Tutong"), ("Seria", "Belait"), ("Kuala Belait", "Belait"),
    ],
}

_faker_locale_cache = {}

def _get_faker(locale: str) -> Faker:
    """Return a cached Faker instance for a locale."""
    if locale not in _faker_locale_cache:
        try:
            _faker_locale_cache[locale] = Faker(locale)
        except Exception:
            _faker_locale_cache[locale] = Faker("en_IN")
    return _faker_locale_cache[locale]

def get_city_and_state(country: str) -> tuple[str, str]:
    """Get a geographically accurate (city, state) pair for the country."""
    if country in CITIES_STATES:
        return random.choice(CITIES_STATES[country])
    return fake_en.city(), fake_en.state()

def get_name_for_gender(country: str, gender: str) -> str:
    """English name 95% of the time; CJK native script allowed only 5% for China/Japan/Korea."""
    use_native = (
        country in CJK_NATIVE_LOCALES
        and random.random() < CJK_NATIVE_CHANCE
    )
    if use_native:
        f = _get_faker(CJK_NATIVE_LOCALES[country])
    else:
        locale = COUNTRY_EN_LOCALES.get(country, "en_IN")
        f = _get_faker(locale)
    try:
        first = f.first_name_male() if gender == "Male" else f.first_name_female()
        last = f.last_name()
        return f"{first} {last}".strip()
    except Exception:
        try:
            return f.name()
        except Exception:
            return fake.name()

def _fill_template(template: str) -> str:
    """Replace each '#' in a phone template with a random digit."""
    return "".join(str(random.randint(0, 9)) if c == "#" else c for c in template)

def get_phone_for_country(country: str) -> str:
    """Get a phone number in the country's local format."""
    if country in COUNTRY_PHONE_LOCALES:
        try:
            return _get_faker(COUNTRY_PHONE_LOCALES[country]).phone_number()
        except Exception:
            pass
    if country in COUNTRY_PHONE_TEMPLATES:
        return _fill_template(random.choice(COUNTRY_PHONE_TEMPLATES[country]))
    return fake.phone_number()

def get_organization_english() -> str:
    """Get an organization/company name in English only."""
    return fake_en.company()

# Realistic email domains: personal/edu for students, org-derived for others
STUDENT_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com",
    "yahoo.co.in", "rediffmail.com", "outlook.co.in",
]
# Country-specific student/edu-style domains (used as extra option for that country)
COUNTRY_STUDENT_DOMAINS = {
    "India": ["ac.in", "edu.in", "gov.in", "res.in"],
    "Australia": ["edu.au", "gov.au"],
    "China": ["edu.cn", "126.com", "qq.com"],
    "Japan": ["ac.jp", "docomo.ne.jp", "yahoo.co.jp"],
    "South Korea": ["ac.kr", "naver.com", "daum.net"],
    "Singapore": ["edu.sg", "gov.sg"],
    "New Zealand": ["ac.nz", "govt.nz"],
    "Pakistan": ["edu.pk", "gov.pk"],
    "Bangladesh": ["edu.bd", "gov.bd"],
    "Sri Lanka": ["ac.lk", "gov.lk"],
    "Philippines": ["edu.ph", "gov.ph"],
    "Vietnam": ["edu.vn", "gov.vn"],
    "Thailand": ["ac.th", "go.th"],
    "Malaysia": ["edu.my", "gov.my"],
    "Indonesia": ["ac.id", "go.id"],
    "Hong Kong": ["edu.hk", "gov.hk"],
    "Taiwan": ["edu.tw", "gov.tw"],
}

def _organization_to_domain(org_name: str, country: str) -> str:
    """Turn organization name into a plausible company domain (e.g. 'Acme Inc' -> acme.com)."""
    # Drop common suffixes and clean
    s = re.sub(r"\s+(Inc\.?|Ltd\.?|LLC|Corp\.?|Co\.?|Pte\.?|L\.?L\.?P\.?|Limited|Private)$", "", org_name, flags=re.IGNORECASE)
    s = re.sub(r"[^\w\s]", "", s)
    s = s.lower().strip().replace(" ", "") or "company"
    s = s[:30]  # avoid overly long domains
    # Prefer .com; use country TLD for local flavour (India -> .co.in, Australia -> .com.au, etc.)
    if random.random() < 0.25 and country in ("India", "Australia", "Singapore"):
        tld = {"India": "co.in", "Australia": "com.au", "Singapore": "com.sg"}.get(country, "com")
    else:
        tld = "com"
    return f"{s}.{tld}"

def generate_email(occupation: str, organization: str, country: str) -> str:
    """Generate a realistic email: student -> personal/edu domains; others -> org-derived domain."""
    local = fake.user_name() + str(random.randint(1, 999))  # avoid collisions
    if occupation == "Student":
        pool = list(STUDENT_DOMAINS)
        if country in COUNTRY_STUDENT_DOMAINS:
            pool.extend(COUNTRY_STUDENT_DOMAINS[country])
        domain = random.choice(pool)
    else:
        domain = _organization_to_domain(organization, country)
    return f"{local}@{domain}"

# Country distribution ratios
countries = {
    "India": 0.40,
    "China": 0.15,
    "Indonesia": 0.07,
    "Japan": 0.07,
    "South Korea": 0.05,
    "Australia": 0.05,
    "Singapore": 0.03,
    "Malaysia": 0.03,
    "Thailand": 0.03,
    "Philippines": 0.03,
    "Vietnam": 0.03,
    "New Zealand": 0.02,
    "Bangladesh": 0.01,
    "Pakistan": 0.01,
    "Sri Lanka": 0.01,
    "Hong Kong": 0.01,
    "Taiwan": 0.01,
    "Nepal": 0.01,
    "Cambodia": 0.005,
    "Laos": 0.005,
    "Myanmar": 0.005,
    "Mongolia": 0.005,
    "Brunei": 0.005
}

occupations = [
    "Student",
    "Professional",
    "Startup",
    "Freelancer"
]

designations = [
    "Software Engineer",
    "Data Analyst",
    "Product Manager",
    "Founder",
    "Research Scientist",
    "Consultant",
    "Student",
    "Marketing Manager"
]

genders = ["Male", "Female"]

records = []

N = int(os.environ.get("GEN_N", "100000"))   # set GEN_N=20 for quick test
OUTPUT_CSV = "apac_users_dataset.csv"
PROGRESS_INTERVAL = 10_000

country_list = list(countries.keys())
weights = list(countries.values())

logger.info("Starting data generation: N=%s, output=%s", N, OUTPUT_CSV)
start_time = time.perf_counter()

try:
    for i in range(N):
        country = random.choices(country_list, weights=weights)[0]
        gender = random.choice(genders)
        city, state = get_city_and_state(country)
        name = get_name_for_gender(country, gender)
        organization = get_organization_english()
        occupation = random.choice(occupations)
        designation = random.choice(designations)
        email = generate_email(occupation, organization, country)
        phone = get_phone_for_country(country)
        records.append({
            "name": name,
            "email": email,
            "phone": phone,
            "gender": gender,
            "occupation": occupation,
            "designation": designation,
            "organization": organization,
            "city": city,
            "state": state,
            "country": country
        })
        if (i + 1) % PROGRESS_INTERVAL == 0:
            logger.info("Progress: %s / %s records generated", i + 1, N)

    gen_elapsed = time.perf_counter() - start_time
    logger.info("Record generation complete: %s records in %.2f s", len(records), gen_elapsed)

    logger.info("Building DataFrame...")
    df = pd.DataFrame(records)

    logger.info("Writing CSV to %s...", OUTPUT_CSV)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    total_elapsed = time.perf_counter() - start_time
    logger.info("Done. Dataset: %s rows, written to %s (total %.2f s)", len(df), OUTPUT_CSV, total_elapsed)

except Exception as e:
    logger.exception("Data generation failed: %s", e)
    raise