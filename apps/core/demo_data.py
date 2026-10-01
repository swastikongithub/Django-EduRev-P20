"""
Static data for `manage.py seed_demo`.

A fictional but believable LPU campus (Phagwara, Punjab). Every person here is
invented; every e-mail address uses the reserved ``lpu.example`` domain. Kept out
of the command so the seeding logic stays readable.
"""

from datetime import date

EMAIL_DOMAIN = "lpu.example"

INSTITUTION = {"code": "LPU", "name": "Lovely Professional University", "short_name": "LPU"}

# ── Organisation ────────────────────────────────────────────────────────────

DEPARTMENTS = [
    ("CSE", "Computer Science & Engineering", "School of Computer Science & Engineering"),
    ("ECE", "Electronics & Communication Engineering", "School of Electronics & Electrical Engineering"),
    ("MEC", "Mechanical Engineering", "School of Mechanical Engineering"),
    ("LSB", "Business Administration", "School of Business (LSB)"),
    ("DES", "Communication & Product Design", "School of Design"),
    ("MTH", "Mathematics", "School of Physical & Mathematical Sciences"),
    ("SPT", "Physical Education & Sports", "Department of Sports"),
    ("EFO", "Estate & Facilities", "Administration"),
    ("ITS", "IT Services", "Administration"),
]

PROGRAMMES = {
    "CSE": "B.Tech. Computer Science & Engineering",
    "ECE": "B.Tech. Electronics & Communication Engineering",
    "MEC": "B.Tech. Mechanical Engineering",
    "LSB": "MBA (Business Analytics)",
    "DES": "B.Des. Communication Design",
    "MTH": "B.Sc. (Hons.) Mathematics",
    "SPT": "B.P.Ed. Physical Education",
}

SECTIONS = {
    "CSE": ["K22FS", "K22FT", "K23KF", "K23KG", "K23GH", "K24CX", "K24CY"],
    "ECE": ["K22EP", "K23EA", "K23EB", "K24EC"],
    "MEC": ["K23ME", "K24MF"],
    "LSB": ["Q23MB", "Q23MC", "Q24MA"],
    "DES": ["D23DA", "D24DB"],
    "MTH": ["K23MS", "K24MS"],
    "SPT": ["P23PE"],
}

# Weighted share of the ~120 background students per department.
STUDENT_MIX = [("CSE", 55), ("ECE", 13), ("MEC", 8), ("LSB", 10), ("DES", 8), ("MTH", 4), ("SPT", 2)]
BACKGROUND_STUDENTS = 120

# Named demo personas. Stable usernames — the login page offers them one-click.
PERSONAS = [
    {
        "username": "student",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "role": "student",
        "dept": "CSE",
        "vid": "12320481",
        "section": "K23KF",
        "programme": PROGRAMMES["CSE"],
        "phone": "98xxxx4810",
    },
    {
        "username": "student2",
        "first_name": "Kabir",
        "last_name": "Malhotra",
        "role": "student",
        "dept": "CSE",
        "vid": "12321174",
        "section": "K23KG",
        "programme": PROGRAMMES["CSE"],
        "phone": "98xxxx1174",
    },
    {
        "username": "faculty",
        "first_name": "Neha",
        "last_name": "Verma",
        "role": "faculty",
        "dept": "CSE",
        "vid": "31245",
        "designation": "Associate Professor, School of CSE",
    },
    {
        "username": "custodian",
        "first_name": "Rajinder",
        "last_name": "Singh",
        "role": "custodian",
        "dept": "CSE",
        "vid": "30871",
        "designation": "Lab Superintendent · Blocks 34 & 38",
    },
    {
        "username": "hod",
        "first_name": "Vikram",
        "last_name": "Sethi",
        "role": "dept_head",
        "dept": "CSE",
        "vid": "30112",
        "designation": "Professor & Head of Department, CSE",
    },
    {
        "username": "facility",
        "first_name": "Harpreet",
        "last_name": "Dhillon",
        "role": "facility_manager",
        "dept": "EFO",
        "vid": "30455",
        "designation": "Facility Manager, Estate & Facilities",
    },
    {
        "username": "admin",
        "first_name": "Anjali",
        "last_name": "Mehta",
        "role": "admin",
        "dept": "ITS",
        "vid": "30018",
        "designation": "System Administrator, LPU Reserve",
        "is_staff": True,
        "is_superuser": True,
    },
]

# Background faculty & staff (username = VID, UMS style).
# (vid, first, last, role, dept, designation)
STAFF = [
    ("30502", "Gurpreet", "Kaur", "custodian", "ECE", "Lab Custodian · Block 33 electronics labs"),
    ("30618", "Baldev", "Raj", "custodian", "SPT", "Sports Officer · Sports Complex"),
    ("30733", "Sunil", "Kumar", "custodian", "MEC", "Technical Officer · Fab Lab & Instrumentation"),
    ("30790", "Pooja", "Rani", "custodian", "DES", "Media & Studios In-charge"),
    ("30244", "Mohit", "Chauhan", "custodian", "EFO", "Estate Supervisor · Academic blocks"),
    ("30367", "Jaswinder", "Pal", "custodian", "EFO", "Transport In-charge"),
    ("30121", "Anita", "Joshi", "dept_head", "ECE", "Professor & Head of Department, ECE"),
    ("30135", "Rakesh", "Bhatia", "dept_head", "MEC", "Professor & Head of Department, MEC"),
    ("30147", "Meenakshi", "Iyer", "dept_head", "LSB", "Professor & Head, School of Business"),
    ("30159", "Farhan", "Qureshi", "dept_head", "DES", "Professor & Head, School of Design"),
    ("31302", "Amit", "Khanna", "faculty", "CSE", "Associate Professor"),
    ("31318", "Priya", "Nair", "faculty", "CSE", "Assistant Professor"),
    ("31327", "Rohit", "Saini", "faculty", "CSE", "Assistant Professor"),
    ("31339", "Kavita", "Arora", "faculty", "CSE", "Associate Professor"),
    ("31346", "Deepak", "Rana", "faculty", "CSE", "Assistant Professor"),
    ("31358", "Sneha", "Kulkarni", "faculty", "CSE", "Assistant Professor"),
    ("31411", "Arjun", "Menon", "faculty", "ECE", "Associate Professor"),
    ("31425", "Ritu", "Chaudhary", "faculty", "ECE", "Assistant Professor"),
    ("31437", "Naveen", "Reddy", "faculty", "ECE", "Assistant Professor"),
    ("31512", "Harish", "Thakur", "faculty", "MEC", "Associate Professor"),
    ("31526", "Simran", "Gill", "faculty", "MEC", "Assistant Professor"),
    ("31604", "Nikhil", "Agarwal", "faculty", "LSB", "Assistant Professor"),
    ("31619", "Swati", "Bedi", "faculty", "LSB", "Associate Professor"),
    ("31707", "Tanvi", "Deshpande", "faculty", "DES", "Assistant Professor"),
    ("31801", "Suresh", "Pillai", "faculty", "MTH", "Associate Professor"),
    ("32011", "Rahul", "Gupta", "staff", "CSE", "Placement Coordinator, CSE"),
    ("32027", "Shalini", "Rawat", "staff", "EFO", "Student Welfare Officer"),
    ("32039", "Manjit", "Sandhu", "staff", "SPT", "Basketball Coach"),
]

FIRST_NAMES_M = [
    "Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan", "Karan",
    "Harsh", "Manav", "Yash", "Siddharth", "Dev", "Parth", "Aman", "Harman", "Jaskaran", "Ankit",
    "Nikhil", "Pranav", "Rahul", "Varun", "Tushar", "Abhishek", "Kunal", "Mohit", "Sahil", "Tanmay",
    "Rishabh", "Akash", "Lakshay", "Navdeep", "Prabhjot", "Ayush", "Keshav", "Shubham", "Vishal", "Gagandeep",
]  # fmt: skip
FIRST_NAMES_F = [
    "Ananya", "Diya", "Saanvi", "Aadhya", "Ishita", "Kavya", "Priya", "Riya", "Sneha", "Pooja",
    "Simran", "Harleen", "Jasleen", "Navneet", "Tanya", "Mehak", "Nandini", "Shreya", "Aditi", "Khushi",
    "Muskan", "Palak", "Sakshi", "Anjali", "Divya", "Isha", "Komal", "Manpreet", "Nisha", "Radhika",
    "Sanya", "Tanvi", "Vaishnavi", "Yashika", "Bhavna", "Charu", "Gauri", "Lavanya", "Meera", "Rupinder",
]  # fmt: skip
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Singh", "Sandhu", "Gill", "Dhillon", "Sidhu", "Brar", "Bajwa",
    "Grewal", "Malhotra", "Kapoor", "Khanna", "Mehta", "Arora", "Bansal", "Aggarwal", "Jain", "Chopra",
    "Bhatia", "Saini", "Rana", "Thakur", "Chauhan", "Yadav", "Mishra", "Pandey", "Tiwari", "Nair",
    "Menon", "Reddy", "Rao", "Iyer", "Kulkarni", "Deshpande", "Joshi", "Patel", "Das", "Mukherjee",
    "Bose", "Sethi", "Anand", "Goyal", "Mittal", "Walia",
]  # fmt: skip

# ── Campus ──────────────────────────────────────────────────────────────────

BUILDINGS = [
    ("18", "Block 18", "Admin Zone", "Administrative block with the Central Auditorium and the senate rooms.", 48, 18),
    ("32", "Block 32", "Academic Zone", "Shared lecture theatres, general classrooms and a seminar hall.", 36, 38),
    ("33", "Block 33", "Academic Zone", "Electronics & communication labs and ECE classrooms.", 44, 46),
    ("34", "Block 34", "Academic Zone", "School of Computer Science & Engineering — classrooms and programming labs.", 55, 42),
    ("36", "Block 36", "Academic Zone", "Mechanical workshops and the Fab Lab (3D printing, drones).", 66, 50),
    ("37", "Block 37", "Academic Zone", "School of Business — case rooms, board room and seminar hall.", 30, 56),
    ("38", "Block 38", "Academic Zone", "CSE research labs: deep learning, cyber security, server room.", 62, 34),
    ("26", "Block 26", "Research Park", "Central Research & Instrumentation Facility.", 78, 28),
    ("25", "Block 25", "Design Quarter", "School of Design studios and the media equipment store.", 22, 70),
    ("13", "Block 13", "Uni Mall", "Student activity block at Uni Mall: music room and recording studio.", 50, 72),
    ("SPC", "Sports Complex", "Sports Complex", "Outdoor courts, football ground, indoor badminton hall and fitness centre.", 84, 76),
    ("TRN", "Transport Depot", "Service Zone", "University buses and vans; trips leave from Gate 2.", 12, 88),
]  # fmt: skip

# Seminar halls & lecture theatres are booked by staff-side roles; students ask a faculty coordinator.
STAFF_ONLY = ["faculty", "staff", "custodian", "dept_head", "facility_manager", "admin"]
VEHICLE_ROLES = ["faculty", "staff", "dept_head", "facility_manager", "admin"]

# code, name, plural, category, icon, accent, allowed_roles, sort_order, description
RESOURCE_TYPES = [
    ("classroom", "Classroom", "Classrooms", "space", "door-open", "orange", [], 10,
     "Standard teaching rooms for make-up classes, tutorials and club meetings."),
    ("lecture-theatre", "Lecture Theatre", "Lecture Theatres", "space", "presentation", "amber", STAFF_ONLY, 20,
     "Large tiered rooms for combined classes, guest lectures and tests. Booked by faculty and staff."),
    ("computer-lab", "Computer Lab", "Computer Labs", "lab", "monitor", "blue", [], 30,
     "Programming and specialised computing labs outside timetabled practicals."),
    ("electronics-lab", "Electronics Lab", "Electronics Labs", "lab", "cpu", "indigo", [], 40,
     "Bench labs with power supplies, oscilloscopes and development boards."),
    ("seminar-hall", "Seminar Hall", "Seminar Halls", "space", "mic", "ink", STAFF_ONLY, 50,
     "Halls for talks, workshops and events. Students ask a faculty coordinator to book."),
    ("meeting-room", "Meeting Room", "Meeting Rooms", "space", "users", "blue", [], 60,
     "Small rooms and pods for project meetings, interviews and reviews."),
    ("sports", "Sports Facility", "Sports Facilities", "sports", "trophy", "green", [], 70,
     "Courts, grounds and the fitness centre at the Sports Complex."),
    ("equipment", "Equipment", "Equipment", "equipment", "camera", "indigo", [], 80,
     "Bookable kit: cameras, 3D printers, oscilloscopes, VR headsets, drones and research instruments."),
    ("vehicle", "Vehicle", "Vehicles", "vehicle", "bus", "ink", VEHICLE_ROLES, 90,
     "University buses and vans for industrial visits, sports travel and outreach."),
    ("studio", "Studio", "Studios", "space", "palette", "amber", [], 100,
     "Music, recording and design studios."),
]  # fmt: skip

# name, icon (lucide), extra search keywords
FEATURES = [
    ("Projector", "projector", "beamer display screen"),
    ("Smart board", "monitor", "interactive panel touch smartboard"),
    ("Air conditioned", "snowflake", "ac cooling"),
    ("60 PCs", "monitor", "computers desktops workstations"),
    ("GPU workstations", "cpu", "cuda nvidia deep learning ml"),
    ("Wheelchair access", "accessibility", "ramp lift accessible"),
    ("Video conferencing", "video", "zoom teams webex hybrid"),
    ("Sound system", "volume-2", "pa speakers microphone audio"),
    ("Floodlights", "lightbulb", "night lights evening"),
    ("Whiteboard", "pencil", "marker board"),
    ("Lab bench power", "zap", "dc supply bench sockets"),
    ("Stage", "mic", "podium event"),
    ("Wi-Fi", "wifi", "internet eduroam"),
    ("Tiered seating", "users", "auditorium style amphitheatre"),
    ("Changing rooms", "users", "lockers showers"),
    ("Soundproofed", "volume-2", "acoustic isolation quiet"),
]

# Illustration keys available at static/img/resources/<key>.webp
ART_KEYS = {
    "classroom", "lecture-theatre", "computer-lab", "electronics-lab", "seminar-hall", "auditorium",
    "meeting-room", "conference-room", "basketball-court", "badminton-court", "football-ground", "gym",
    "3d-printer", "oscilloscope", "dslr-camera", "projector", "vr-headset", "drone", "bus", "music-room",
    "design-studio", "gpu-server", "microscope", "tennis-court",
}  # fmt: skip

LAKH = 100_000


def _r(code, type_, name, building, *, cap, art, dept=None, floor="", room="", features=(), attrs=(), desc="",
       tagline="", cost=None, custodian=None, status="active", status_note=""):  # fmt: skip
    return {
        "code": code,
        "type": type_,
        "name": name,
        "building": building,
        "capacity": cap,
        "art": art,
        "dept": dept,
        "floor": floor,
        "room": room,
        "features": list(features),
        "attrs": list(attrs),
        "description": desc,
        "tagline": tagline,
        "cost": cost,
        "custodian": custodian,
        "status": status,
        "status_note": status_note,
    }


STD_ROOM = ["Projector", "Whiteboard", "Wi-Fi"]

RESOURCES = [
    # Classrooms
    _r("34-301", "classroom", "Classroom 34-301", "34", cap=66, art="classroom", dept="CSE", floor="3", room="301",
       features=STD_ROOM + ["Smart board", "Air conditioned"], attrs=[("Seats", "66 · fixed benches"), ("Board", "Smart board + whiteboard")],
       desc="Air-conditioned room next to the CSE faculty cabins. The smart board records to the LMS if you sign in first.",
       tagline="Smart-board room on the CSE floor", custodian="custodian"),
    _r("34-302", "classroom", "Classroom 34-302", "34", cap=66, art="classroom", dept="CSE", floor="3", room="302",
       features=STD_ROOM + ["Air conditioned"], attrs=[("Seats", "66 · fixed benches")],
       desc="Standard CSE classroom with a ceiling projector. HDMI and USB-C cables are at the lectern.", custodian="custodian"),
    _r("34-303", "classroom", "Classroom 34-303", "34", cap=60, art="classroom", dept="CSE", floor="3", room="303",
       features=STD_ROOM + ["Air conditioned"], attrs=[("Seats", "60 · movable desks")],
       desc="Movable desks make this the easiest room to rearrange for group work. Put the desks back in rows when you leave.", custodian="custodian"),
    _r("34-304", "classroom", "Classroom 34-304", "34", cap=60, art="classroom", dept="CSE", floor="3", room="304",
       features=STD_ROOM, attrs=[("Seats", "60 · fixed benches"), ("Cooling", "Ceiling fans")],
       desc="Fan-cooled room on the quiet side of the corridor. Good for evening doubt-clearing sessions.", custodian="custodian"),
    _r("34-405", "classroom", "Classroom 34-405", "34", cap=72, art="classroom", dept="CSE", floor="4", room="405",
       features=STD_ROOM + ["Air conditioned", "Wheelchair access"], attrs=[("Seats", "72 · fixed benches"), ("Access", "Lift lobby opposite")],
       desc="The largest classroom in Block 34, opposite the lift. Step-free from the ground floor.", custodian="custodian"),
    _r("34-406", "classroom", "Tutorial Room 34-406", "34", cap=30, art="classroom", dept="CSE", floor="4", room="406",
       features=["Whiteboard", "Wi-Fi", "Air conditioned"], attrs=[("Seats", "30 · round tables")],
       desc="Small tutorial room with round tables and a wall-length whiteboard. No projector — bring a laptop and use the TV.", custodian="custodian"),
    _r("32-201", "classroom", "Classroom 32-201", "32", cap=70, art="classroom", dept="MTH", floor="2", room="201",
       features=STD_ROOM, attrs=[("Seats", "70 · fixed benches")],
       desc="General-purpose classroom used for maths and aptitude classes. Two whiteboards, one either side of the screen.", custodian="30244"),
    _r("32-202", "classroom", "Classroom 32-202", "32", cap=70, art="classroom", dept="MTH", floor="2", room="202",
       features=STD_ROOM + ["Air conditioned"], attrs=[("Seats", "70 · fixed benches")],
       desc="General-purpose air-conditioned classroom. The projector remote is kept with the floor attendant.", custodian="30244"),
    _r("33-205", "classroom", "Classroom 33-205", "33", cap=60, art="classroom", dept="ECE", floor="2", room="205",
       features=STD_ROOM, attrs=[("Seats", "60 · fixed benches")],
       desc="ECE classroom one floor above the electronics labs. Handy for a theory recap before a practical.", custodian="30502"),
    _r("37-101", "classroom", "Case Room 37-101", "37", cap=64, art="classroom", dept="LSB", floor="1", room="101",
       features=STD_ROOM + ["Air conditioned", "Tiered seating"], attrs=[("Seats", "64 · horseshoe, tiered"), ("Name cards", "At the lectern")],
       desc="Horseshoe-shaped case-discussion room. Every seat can see every other seat, which is the point.", custodian="30244"),
    _r("37-102", "classroom", "Classroom 37-102", "37", cap=60, art="classroom", dept="LSB", floor="1", room="102",
       features=STD_ROOM + ["Air conditioned"], attrs=[("Seats", "60 · movable desks")],
       desc="Business school classroom with movable desks for syndicate work.", custodian="30244"),
    # Lecture theatres
    _r("32-LT-1", "lecture-theatre", "Lecture Theatre 32-LT1", "32", cap=180, art="lecture-theatre", dept="MTH", floor="G", room="LT1",
       features=["Projector", "Sound system", "Air conditioned", "Tiered seating", "Wheelchair access"],
       attrs=[("Seats", "180 · tiered"), ("Mics", "2 wireless + lectern")],
       desc="Tiered theatre used for combined classes and aptitude tests. Wheelchair spaces are on the front row.", custodian="30244"),
    _r("32-LT-2", "lecture-theatre", "Lecture Theatre 32-LT2", "32", cap=160, art="lecture-theatre", dept="MTH", floor="G", room="LT2",
       features=["Projector", "Sound system", "Air conditioned", "Tiered seating"], attrs=[("Seats", "160 · tiered")],
       desc="Slightly smaller twin of LT1 across the foyer. Rear exit opens onto the Block 32 lawn.", custodian="30244"),
    _r("34-LT-1", "lecture-theatre", "Lecture Theatre 34-LT1", "34", cap=240, art="lecture-theatre", dept="CSE", floor="G", room="LT1",
       features=["Projector", "Sound system", "Air conditioned", "Tiered seating", "Video conferencing", "Wheelchair access"],
       attrs=[("Seats", "240 · tiered"), ("Screens", "Dual projection"), ("Capture", "Lecture capture to LMS")],
       desc="The biggest teaching room in the CSE block, with dual projection and lecture capture. Book it for combined sections and guest lectures.",
       tagline="240 seats, dual screens, lecture capture", custodian="custodian"),
    _r("37-LT-1", "lecture-theatre", "LSB Lecture Theatre", "37", cap=150, art="lecture-theatre", dept="LSB", floor="G", room="LT1",
       features=["Projector", "Sound system", "Air conditioned", "Tiered seating"], attrs=[("Seats", "150 · tiered")],
       desc="Business school lecture theatre with a separate green room behind the stage.", custodian="30244"),
    # Computer labs
    _r("34-LAB-1", "computer-lab", "Programming Lab 34-101", "34", cap=60, art="computer-lab", dept="CSE", floor="1", room="101",
       features=["60 PCs", "Projector", "Air conditioned", "Wheelchair access", "Wi-Fi"],
       attrs=[("OS", "Windows 11 / Ubuntu 24.04 (dual boot)"), ("PCs", "Core i5-12400 · 16 GB RAM"), ("Software", "VS Code, JDK 21, Python 3.12, MySQL 8")],
       desc="General programming lab on the ground floor. Machines reset to a clean image every night, so save work to your drive.",
       tagline="60 dual-boot PCs, ground floor", cost=42 * LAKH, custodian="custodian"),
    _r("34-LAB-2", "computer-lab", "Programming Lab 34-102", "34", cap=60, art="computer-lab", dept="CSE", floor="1", room="102",
       features=["60 PCs", "Projector", "Air conditioned", "Wi-Fi"],
       attrs=[("OS", "Windows 11 / Ubuntu 24.04 (dual boot)"), ("PCs", "Core i5-12400 · 16 GB RAM"), ("Software", "VS Code, JDK 21, Python 3.12, Node 22")],
       desc="Twin of 34-101. Used for most Java and web-programming practicals.", cost=40 * LAKH, custodian="custodian"),
    _r("34-LAB-3", "computer-lab", "Networks Lab 34-208", "34", cap=40, art="computer-lab", dept="CSE", floor="2", room="208",
       features=["Projector", "Air conditioned", "Wi-Fi"],
       attrs=[("PCs", "40 · Core i5"), ("Network kit", "Cisco 2901 routers, Catalyst 2960 switches"), ("Tools", "Packet Tracer, GNS3, Wireshark")],
       desc="Racks of routers and switches for hands-on networking. Re-cable the racks to the default topology before you leave.",
       cost=35 * LAKH, custodian="custodian"),
    _r("38-LAB-1", "computer-lab", "Software Engineering Lab 38-110", "38", cap=60, art="computer-lab", dept="CSE", floor="1", room="110",
       features=["60 PCs", "Projector", "Air conditioned", "Smart board", "Wi-Fi"],
       attrs=[("OS", "Ubuntu 24.04 / Windows 11"), ("PCs", "Core i7-13700 · 32 GB RAM"), ("Software", "IntelliJ, Docker, Git, Android Studio")],
       desc="Faster machines with Docker and Android Studio pre-installed. Popular for capstone sprints and hackathon prep.",
       cost=45 * LAKH, custodian="custodian"),
    _r("38-LAB-2", "computer-lab", "Deep Learning Lab 38-204", "38", cap=30, art="computer-lab", dept="CSE", floor="2", room="204",
       features=["GPU workstations", "Projector", "Air conditioned", "Wi-Fi"],
       attrs=[("GPU", "RTX 4070 12 GB per workstation"), ("OS", "Ubuntu 24.04 LTS"), ("Frameworks", "PyTorch 2, TensorFlow, CUDA 12"), ("Workstations", "30")],
       desc="Thirty GPU workstations for ML coursework and projects. The most requested lab on campus — book early and check in on time.",
       tagline="30 RTX 4070 workstations", cost=60 * LAKH, custodian="custodian"),
    _r("38-LAB-3", "computer-lab", "Cyber Security Lab 38-306", "38", cap=40, art="computer-lab", dept="CSE", floor="3", room="306",
       features=["Projector", "Air conditioned"],
       attrs=[("OS", "Kali Linux / Windows 11"), ("Network", "Air-gapped range, isolated from campus Wi-Fi")],
       desc="Isolated network range for security coursework and CTF practice. Nothing here can reach the campus network, by design.",
       cost=38 * LAKH, custodian="custodian"),
    # Electronics labs
    _r("33-LAB-1", "electronics-lab", "Digital Electronics Lab 33-110", "33", cap=36, art="electronics-lab", dept="ECE", floor="1", room="110",
       features=["Lab bench power", "Projector"], attrs=[("Benches", "18 × 2 seats"), ("Per bench", "DC supply, function generator, 2-ch scope")],
       desc="Eighteen two-seat benches with supplies and scopes. Trainer kits are issued by the custodian against your ID card.",
       cost=22 * LAKH, custodian="30502"),
    _r("33-LAB-2", "electronics-lab", "Analog & Communication Lab 33-112", "33", cap=36, art="oscilloscope", dept="ECE", floor="1", room="112",
       features=["Lab bench power", "Projector", "Air conditioned"], attrs=[("Benches", "18 × 2 seats"), ("Kit", "AM/FM trainers, spectrum analyser")],
       desc="Analog and RF benches with a shared spectrum analyser. The analyser stays in the lab.", cost=26 * LAKH, custodian="30502"),
    _r("33-LAB-3", "electronics-lab", "Embedded Systems & IoT Lab 33-214", "33", cap=30, art="electronics-lab", dept="ECE", floor="2", room="214",
       features=["Lab bench power", "Wi-Fi", "Air conditioned"],
       attrs=[("Boards", "Arduino Uno R4, ESP32, Raspberry Pi 5, STM32 Nucleo"), ("Soldering", "6 stations with fume extraction")],
       desc="Microcontroller boards, sensors and soldering stations for IoT projects. Components are issued per booking.",
       cost=18 * LAKH, custodian="30502"),
    _r("33-LAB-4", "electronics-lab", "VLSI Design Lab 33-305", "33", cap=30, art="electronics-lab", dept="ECE", floor="3", room="305",
       features=["Air conditioned", "Projector"], attrs=[("Tools", "Cadence Virtuoso (academic), Xilinx Vivado"), ("FPGA", "Artix-7 boards × 15")],
       desc="EDA workstations and FPGA boards for VLSI coursework and research. Licences are node-locked to this room.",
       cost=55 * LAKH, custodian="30502"),
    # Seminar halls
    _r("34-SH-1", "seminar-hall", "Block 34 Seminar Hall", "34", cap=150, art="seminar-hall", dept="CSE", floor="5", room="SH",
       features=["Projector", "Sound system", "Air conditioned", "Stage", "Video conferencing", "Wheelchair access"],
       attrs=[("Seats", "150 · cushioned"), ("Mics", "2 wireless + podium"), ("Hybrid", "PTZ camera for online speakers")],
       desc="CSE's hall for guest lectures and workshops, with a PTZ camera for hybrid talks. Requests need custodian approval.",
       tagline="Hybrid-ready hall for 150", custodian="custodian"),
    _r("32-SH-1", "seminar-hall", "Block 32 Seminar Hall", "32", cap=220, art="seminar-hall", dept="ECE", floor="4", room="SH",
       features=["Projector", "Sound system", "Air conditioned", "Stage", "Wheelchair access"], attrs=[("Seats", "220 · cushioned")],
       desc="Campus-wide seminar hall on the top floor of Block 32. Lift access from the main foyer.", custodian="30244"),
    _r("37-SH-1", "seminar-hall", "LSB Seminar Hall", "37", cap=180, art="conference-room", dept="LSB", floor="2", room="SH",
       features=["Projector", "Sound system", "Air conditioned", "Stage", "Video conferencing"], attrs=[("Seats", "180 · cabaret or theatre")],
       desc="Flexible hall that can be set theatre-style or cabaret for case competitions. Tell the custodian the layout in your notes.",
       custodian="30244"),
    _r("18-AUD", "seminar-hall", "Central Auditorium", "18", cap=1200, art="auditorium", dept="EFO", floor="G", room="AUD",
       features=["Projector", "Sound system", "Air conditioned", "Stage", "Tiered seating", "Wheelchair access"],
       attrs=[("Seats", "1,200 (balcony 300)"), ("Stage", "18 m × 10 m with two green rooms"), ("Lighting", "Moving-head rig, 48-channel desk")],
       desc="The campus auditorium for convocation, fests and large conferences. Every request goes to the custodian and then the facility manager.",
       tagline="1,200 seats — two-step approval", custodian="30244"),
    # Meeting rooms
    _r("34-MR-1", "meeting-room", "CSE Faculty Meeting Room 34-510", "34", cap=14, art="conference-room", dept="CSE", floor="5", room="510",
       features=["Video conferencing", "Smart board", "Air conditioned", "Wi-Fi"], attrs=[("Table", "Boardroom, 14 seats")],
       desc="Faculty meeting room with a 75-inch panel and conferencing camera.", custodian="custodian"),
    _r("38-MR-1", "meeting-room", "Project Discussion Pod 38-P1", "38", cap=6, art="meeting-room", dept="CSE", floor="1", room="P1",
       features=["Whiteboard", "Wi-Fi", "Air conditioned"], attrs=[("Screen", "43-inch TV with HDMI")],
       desc="Glass pod for six next to the Block 38 atrium. Ideal for capstone stand-ups and mentor reviews.", custodian="custodian"),
    _r("38-MR-2", "meeting-room", "Project Discussion Pod 38-P2", "38", cap=6, art="meeting-room", dept="CSE", floor="1", room="P2",
       features=["Whiteboard", "Wi-Fi", "Air conditioned"], attrs=[("Screen", "43-inch TV with HDMI")],
       desc="Second glass pod beside 38-P1. Same kit, slightly quieter.", custodian="custodian"),
    _r("37-MR-1", "meeting-room", "LSB Board Room", "37", cap=20, art="conference-room", dept="LSB", floor="3", room="301",
       features=["Video conferencing", "Air conditioned", "Wi-Fi"], attrs=[("Table", "Boardroom, 20 seats")],
       desc="Formal board room used for recruiter meetings and interview panels.", custodian="30244"),
    _r("18-CR-1", "meeting-room", "Senate Conference Room", "18", cap=30, art="conference-room", dept="EFO", floor="1", room="104",
       features=["Video conferencing", "Sound system", "Air conditioned", "Wi-Fi"], attrs=[("Table", "Hollow square, 30 seats")],
       desc="Conference room in the admin block for university committees and external visitors.", custodian="30244"),
    # Sports
    _r("SPT-BB-1", "sports", "Basketball Court 1", "SPC", cap=20, art="basketball-court", dept="SPT", room="Court 1",
       features=["Floodlights", "Changing rooms"], attrs=[("Surface", "Synthetic acrylic"), ("Hoops", "Adjustable, glass boards")],
       desc="Floodlit outdoor court nearest the hostels. Evenings fill up fast in the inter-hostel league season.",
       tagline="Floodlit — busiest court on campus", custodian="30618"),
    _r("SPT-BB-2", "sports", "Basketball Court 2", "SPC", cap=20, art="basketball-court", dept="SPT", room="Court 2",
       features=["Floodlights"], attrs=[("Surface", "Synthetic acrylic")],
       desc="Second floodlit court beside Court 1. The university squad practises here early mornings.", custodian="30618"),
    _r("SPT-BD-1", "sports", "Badminton Court 1 (Indoor)", "SPC", cap=4, art="badminton-court", dept="SPT", floor="G", room="Hall A-1",
       features=["Changing rooms"], attrs=[("Surface", "Wooden with synthetic mat"), ("Hall", "Indoor Hall A")],
       desc="Indoor court with a synthetic mat over sprung wood. Non-marking shoes only.", custodian="30618"),
    _r("SPT-BD-2", "sports", "Badminton Court 2 (Indoor)", "SPC", cap=4, art="badminton-court", dept="SPT", floor="G", room="Hall A-2",
       features=["Changing rooms"], attrs=[("Surface", "Wooden with synthetic mat")],
       desc="Indoor court in Hall A. Racquets and shuttles can be requested with the booking.", custodian="30618"),
    _r("SPT-BD-3", "sports", "Badminton Court 3 (Indoor)", "SPC", cap=4, art="badminton-court", dept="SPT", floor="G", room="Hall A-3",
       features=["Changing rooms"], attrs=[("Surface", "Wooden with synthetic mat")],
       desc="Corner court in Hall A, beside the service door. Slightly cooler than courts 1 and 2 in the afternoon.", custodian="30618"),
    _r("SPT-FB-1", "sports", "Football Ground", "SPC", cap=30, art="football-ground", dept="SPT", room="Ground 1",
       features=["Floodlights", "Changing rooms"], attrs=[("Surface", "Natural grass"), ("Size", "Full size, 105 × 68 m")],
       desc="Full-size natural grass pitch. Studs are fine; the ground is rested on Mondays until noon.", custodian="30618"),
    _r("SPT-TN-1", "sports", "Tennis Court 1", "SPC", cap=4, art="tennis-court", dept="SPT", room="Court T1",
       features=["Floodlights"], attrs=[("Surface", "Synthetic hard court")],
       desc="Floodlit hard court. Bring your own balls; racquets are at the equipment desk.", custodian="30618"),
    _r("SPT-GYM-1", "sports", "Fitness Centre", "SPC", cap=40, art="gym", dept="SPT", floor="1", room="FC",
       features=["Air conditioned", "Changing rooms", "Sound system"], attrs=[("Kit", "Free weights, 12 cardio machines, 4 racks")],
       desc="Book the fitness centre for team conditioning sessions. Drop-in gym hours for individuals are separate.", custodian="30618"),
    # Equipment
    _r("EQ-CAM-01", "equipment", "Sony A7 IV Camera Kit", "25", cap=1, art="dslr-camera", dept="DES", room="Media store",
       attrs=[("Sensor", "33 MP full-frame"), ("Lens", "24–70 mm f/4"), ("Includes", "2 batteries, 128 GB card, shoulder bag")],
       desc="Full-frame mirrorless kit for coursework and event coverage. Collect from and return to the Block 25 media store.",
       cost=2.6 * LAKH, custodian="30790"),
    _r("EQ-CAM-02", "equipment", "Canon EOS R6 Camera Kit", "25", cap=1, art="dslr-camera", dept="DES", room="Media store",
       attrs=[("Sensor", "20 MP full-frame"), ("Lens", "24–105 mm f/4"), ("Includes", "2 batteries, 64 GB card")],
       desc="Second camera kit with excellent low-light autofocus. Check the sensor for dust when you collect it.",
       cost=2.4 * LAKH, custodian="30790"),
    _r("EQ-PRJ-01", "equipment", "Portable Laser Projector", "25", cap=1, art="projector", dept="DES", room="Media store",
       attrs=[("Brightness", "4,000 lumens"), ("Includes", "Tripod screen 100-inch, HDMI 10 m")],
       desc="Portable projector and screen for outdoor screenings and club events.", cost=1.1 * LAKH, custodian="30790"),
    _r("EQ-3DP-01", "equipment", "Ultimaker S5 3D Printer", "36", cap=1, art="3d-printer", dept="MEC", room="Fab Lab",
       attrs=[("Build volume", "330 × 240 × 300 mm"), ("Materials", "PLA, PETG, ABS, TPU"), ("Slicer", "Cura, on the Fab Lab PC")],
       desc="Workhorse FDM printer in the Fab Lab. Upload a sliced file before your slot — the booking is for machine time.",
       cost=6.5 * LAKH, custodian="30733"),
    _r("EQ-3DP-02", "equipment", "Industrial SLA 3D Printer", "36", cap=1, art="3d-printer", dept="MEC", room="Fab Lab",
       attrs=[("Build volume", "335 × 200 × 300 mm"), ("Resolution", "25 µm layers"), ("Materials", "Standard, tough and dental resins")],
       desc="High-resolution resin printer for precision parts. First-time users need a 30-minute induction with the Fab Lab officer.",
       cost=12 * LAKH, custodian="30733"),
    _r("EQ-OSC-01", "equipment", "Keysight 4-Channel Oscilloscope (200 MHz)", "33", cap=1, art="oscilloscope", dept="ECE", room="33-112 store",
       attrs=[("Bandwidth", "200 MHz"), ("Channels", "4 analog"), ("Sample rate", "2 GSa/s")],
       desc="Bench scope for project debugging outside lab hours. Probes are issued with the booking.",
       cost=3.8 * LAKH, custodian="30502"),
    _r("EQ-OSC-02", "equipment", "Mixed-Signal Oscilloscope (1 GHz)", "33", cap=1, art="oscilloscope", dept="ECE", room="33-305 store",
       attrs=[("Bandwidth", "1 GHz"), ("Channels", "4 analog + 16 digital"), ("Decoding", "I²C, SPI, UART, CAN")],
       desc="High-bandwidth scope with protocol decoding for research and final-year projects.", cost=9.5 * LAKH, custodian="30502"),
    _r("EQ-VR-01", "equipment", "Meta Quest 3 VR Kit", "38", cap=1, art="vr-headset", dept="CSE", room="38-204 store",
       attrs=[("Includes", "Headset, 2 controllers, charging dock"), ("Tracking", "Inside-out, 6DoF")],
       desc="Standalone VR headset for XR coursework and user studies. Wipe it down with the supplied covers after use.",
       cost=0.65 * LAKH, custodian="custodian"),
    _r("EQ-VR-02", "equipment", "Meta Quest 3 VR Kit #2", "38", cap=1, art="vr-headset", dept="CSE", room="38-204 store",
       attrs=[("Includes", "Headset, 2 controllers, charging dock")],
       desc="Second VR kit, same set-up as kit #1.", cost=0.65 * LAKH, custodian="custodian",
       status="out_of_service", status_note="Left lens cracked — replacement part on order"),
    _r("EQ-DRN-01", "equipment", "DJI Mavic 3 Drone Kit", "36", cap=1, art="drone", dept="MEC", room="Fab Lab",
       attrs=[("Camera", "4/3 CMOS, 5.1K video"), ("Flight time", "~40 min per battery"), ("Rule", "Fly only over the Sports Complex with a certified pilot")],
       desc="Survey and media drone. A certified pilot from the Fab Lab accompanies every flight.", cost=2.2 * LAKH, custodian="30733"),
    _r("EQ-SEM-01", "equipment", "Scanning Electron Microscope", "26", cap=1, art="microscope", dept="MEC", floor="G", room="CRIF-02",
       attrs=[("Resolution", "3 nm at 30 kV"), ("Detectors", "SE, BSE, EDS"), ("Operator", "Trained operator required")],
       desc="Research-grade SEM with EDS for materials characterisation. Samples must be dry and coated; the operator runs the session.",
       tagline="₹38 lakh instrument — trained operator", cost=38 * LAKH, custodian="30733"),
    _r("EQ-GPU-01", "equipment", "GPU Compute Node (4× RTX 6000 Ada)", "38", cap=1, art="gpu-server", dept="CSE", room="Server room 38-B1",
       attrs=[("GPUs", "4× RTX 6000 Ada, 48 GB each"), ("CPU / RAM", "2× Xeon Gold · 512 GB"), ("Access", "SSH via campus VPN; slot = exclusive node")],
       desc="Exclusive time on a four-GPU node for training runs too large for the lab workstations. Jobs are killed at the end of the slot.",
       cost=28 * LAKH, custodian="custodian"),
    # Vehicles
    _r("VEH-BUS-3", "vehicle", "University Bus 3 (52-seater)", "TRN", cap=52, art="bus", dept="EFO", room="Bay 3",
       attrs=[("Registration", "PB-08-EX-4103"), ("Seats", "52 + driver"), ("Driver", "Included")],
       desc="Air-conditioned coach for industrial visits and team travel. The driver's duty hours limit day trips to about 11 hours.",
       cost=38 * LAKH, custodian="30367"),
    _r("VEH-BUS-5", "vehicle", "University Bus 5 (41-seater)", "TRN", cap=41, art="bus", dept="EFO", room="Bay 5",
       attrs=[("Registration", "PB-08-EX-4105"), ("Seats", "41 + driver")],
       desc="Non-AC bus used for short trips around Phagwara and Jalandhar.", cost=32 * LAKH, custodian="30367"),
    _r("VEH-VAN-1", "vehicle", "Tempo Traveller (14-seater)", "TRN", cap=14, art="bus", dept="EFO", room="Bay 7",
       attrs=[("Registration", "PB-08-EX-2207"), ("Seats", "14 + driver")],
       desc="Van for small teams, guest pick-ups and airport runs.", cost=18 * LAKH, custodian="30367"),
    # Studios
    _r("13-STU-1", "studio", "Music Room 13-G04", "13", cap=15, art="music-room", dept="DES", floor="G", room="G04",
       features=["Soundproofed", "Sound system", "Air conditioned"], attrs=[("Instruments", "Upright piano, drum kit, 2 guitar amps, tabla set")],
       desc="Rehearsal room for bands and ensembles. Keep the drum kit on the rug.", custodian="30790"),
    _r("13-STU-2", "studio", "Recording Studio 13-G06", "13", cap=6, art="music-room", dept="DES", floor="G", room="G06",
       features=["Soundproofed", "Air conditioned"], attrs=[("Booth", "Isolated vocal booth"), ("Interface", "8-channel, Logic Pro & Reaper")],
       desc="Small recording studio with an isolated vocal booth, used for podcasts and demos.", cost=14 * LAKH, custodian="30790"),
    _r("25-DS-1", "studio", "Design Studio 25-301", "25", cap=40, art="design-studio", dept="DES", floor="3", room="301",
       features=["Projector", "Air conditioned", "Wi-Fi"], attrs=[("Tables", "40 drafting tables"), ("Pin-up", "Full-wall pin-up boards")],
       desc="Studio with drafting tables and pin-up walls for crits and model making.", custodian="30790"),
    _r("25-DS-2", "studio", "Mac Design Studio 25-305", "25", cap=30, art="design-studio", dept="DES", floor="3", room="305",
       features=["Projector", "Air conditioned", "Wi-Fi"], attrs=[("Machines", "30 iMac 24-inch"), ("Software", "Adobe Creative Cloud, Figma, Blender")],
       desc="iMac studio for digital design coursework and portfolio work.", cost=36 * LAKH, custodian="30790"),
]  # fmt: skip

# ── Rules ───────────────────────────────────────────────────────────────────

CAMPUS_POLICY = {
    "slot_minutes": 30,
    "min_duration_minutes": 30,
    "max_duration_minutes": 180,
    "lead_time_minutes": 0,
    "max_advance_days": 30,
    "checkin_grace_minutes": 15,
}

TYPE_POLICIES = {
    "classroom": {"slot_minutes": 30, "min_duration_minutes": 30, "max_duration_minutes": 180, "max_advance_days": 30},
    "lecture-theatre": {
        "slot_minutes": 30,
        "min_duration_minutes": 60,
        "max_duration_minutes": 180,
        "max_advance_days": 30,
    },
    "computer-lab": {
        "slot_minutes": 30,
        "min_duration_minutes": 30,
        "max_duration_minutes": 180,
        "max_advance_days": 30,
    },
    "electronics-lab": {
        "slot_minutes": 30,
        "min_duration_minutes": 60,
        "max_duration_minutes": 180,
        "max_advance_days": 30,
    },
    "seminar-hall": {
        "slot_minutes": 30,
        "min_duration_minutes": 60,
        "max_duration_minutes": 480,
        "lead_time_minutes": 1440,
        "max_advance_days": 60,
        "checkin_grace_minutes": 30,
    },
    "meeting-room": {
        "slot_minutes": 30,
        "min_duration_minutes": 30,
        "max_duration_minutes": 180,
        "max_advance_days": 14,
    },
    "sports": {
        "slot_minutes": 60,
        "min_duration_minutes": 60,
        "max_duration_minutes": 120,
        "max_advance_days": 7,
        "checkin_grace_minutes": 10,
    },
    "equipment": {
        "slot_minutes": 30,
        "min_duration_minutes": 30,
        "max_duration_minutes": 240,
        "lead_time_minutes": 60,
        "max_advance_days": 21,
        "checkin_opens_minutes": 30,
        "checkin_grace_minutes": 30,
    },
    "vehicle": {
        "slot_minutes": 30,
        "min_duration_minutes": 60,
        "max_duration_minutes": 720,
        "lead_time_minutes": 2880,
        "max_advance_days": 30,
        "checkin_opens_minutes": 30,
        "checkin_grace_minutes": 30,
    },
    "studio": {"slot_minutes": 30, "min_duration_minutes": 60, "max_duration_minutes": 180, "max_advance_days": 14},
}

RESOURCE_POLICIES = {
    "EQ-SEM-01": {
        "slot_minutes": 60,
        "min_duration_minutes": 60,
        "max_duration_minutes": 240,
        "lead_time_minutes": 1440,
        "max_advance_days": 30,
        "checkin_grace_minutes": 30,
    },
    "18-AUD": {
        "slot_minutes": 60,
        "min_duration_minutes": 120,
        "max_duration_minutes": 720,
        "lead_time_minutes": 4320,
        "max_advance_days": 90,
        "checkin_grace_minutes": 30,
    },
}

MON_SAT = [0, 1, 2, 3, 4, 5]
MON_FRI = [0, 1, 2, 3, 4]
ALL_WEEK = [0, 1, 2, 3, 4, 5, 6]

# type -> (weekdays, opens, closes)
HOURS = {
    "classroom": (MON_SAT, "08:00", "20:00"),
    "lecture-theatre": (MON_SAT, "08:00", "20:00"),
    "seminar-hall": (MON_SAT, "08:00", "20:00"),
    "meeting-room": (MON_SAT, "08:00", "20:00"),
    "computer-lab": (MON_SAT, "08:00", "21:00"),
    "electronics-lab": (MON_SAT, "08:00", "21:00"),
    "studio": (MON_SAT, "09:00", "21:00"),
    "sports": (ALL_WEEK, "06:00", "22:00"),
    "equipment": (MON_FRI, "09:00", "18:00"),
    "vehicle": (ALL_WEEK, "06:00", "22:00"),
}

# title, kind, scope, target (type code / resource code / None), start, end, exempt_roles, note
BLACKOUTS = [
    ("Diwali break", "holiday", "campus", None, "2026-11-07 00:00", "2026-11-11 00:00", [],
     "Campus closed for Diwali, 7–10 November. Hostels stay open; academic blocks are locked."),
    ("Mid-term examinations", "restricted", "type", "seminar-hall", "2026-10-19 00:00", "2026-10-25 00:00",
     ["faculty", "dept_head", "facility_manager", "admin"],
     "Seminar halls double as exam venues during mid-terms. Only faculty and administrators can book them this week."),
    ("Innovate 2026 tech fest — set-up and shows", "event", "resource", "18-AUD", "2026-10-08 06:00", "2026-10-10 22:00", [],
     "The auditorium is held for the annual tech fest, including stage build and rehearsals."),
]  # fmt: skip

# name, role, dept code, type code, period, max_hours, max_bookings
QUOTAS = [
    ("Student weekly booking hours", "student", None, None, "week", 6, None),
    ("Student daily bookings", "student", None, None, "day", None, 2),
    ("Student equipment hours", "student", None, "equipment", "week", 8, None),
    ("CSE seminar hall hours", "", "CSE", "seminar-hall", "month", 40, None),
    ("Faculty weekly booking hours", "faculty", None, None, "week", 20, None),
]

# no_shows, window_days, restrict_days, label
RESTRICTION_TIERS = [
    (2, 30, 0, "Warning"),
    (3, 30, 7, "7-day pause"),
    (5, 60, 30, "30-day pause"),
]

# name, description, type code, resource code, requester_roles, min_attendees, min_duration, auto, priority, steps
# steps: [(approver_role, sla_hours)]
WORKFLOWS = [
    ("Seminar hall · faculty request", "Faculty requests are confirmed by the hall's custodian.",
     "seminar-hall", None, ["faculty"], None, None, False, 100, [("custodian", 24)]),
    ("Seminar hall · staff & other requests", "Custodian checks logistics, then the owning department's head approves.",
     "seminar-hall", None, [], None, None, False, 50, [("custodian", 24), ("dept_head", 48)]),
    ("Equipment · student request", "Students borrowing equipment are approved by the kit's custodian.",
     "equipment", None, ["student"], None, None, False, 100, [("custodian", 12)]),
    ("Vehicle requisition", "Every vehicle trip is approved by the facility manager (driver roster, fuel).",
     "vehicle", None, [], None, None, False, 100, [("facility_manager", 24)]),
    ("Central Auditorium", "Custodian confirms stage and crew; the facility manager signs off on security and power.",
     None, "18-AUD", [], None, None, False, 100, [("custodian", 24), ("facility_manager", 48)]),
    ("Computer lab · faculty auto-confirm", "Faculty lab bookings are confirmed instantly.",
     "computer-lab", None, ["faculty"], None, None, True, 100, []),
    ("Sports · long student sessions", "Two-hour student sessions need the sports officer's OK.",
     "sports", None, ["student"], None, 120, False, 100, [("custodian", 12)]),
]  # fmt: skip

# ── Timetable ───────────────────────────────────────────────────────────────

TERM = {"code": "26271", "name": "2026-27 Odd", "starts": date(2026, 8, 1), "ends": date(2026, 12, 15)}

COURSES = {
    "cse": [
        ("CSE310", "Programming in Java"),
        ("CSE316", "Operating Systems"),
        ("CSE408", "Design and Analysis of Algorithms"),
        ("CSE322", "Formal Languages and Automation Theory"),
        ("INT306", "Database Management Systems"),
        ("INT404", "Artificial Intelligence"),
        ("CSE211", "Computer Organization and Design"),
        ("INT253", "Linux Administration"),
    ],
    "cse_lab": [
        ("CSE326", "Internet Programming Laboratory"),
        ("CSE325", "Operating Systems Laboratory"),
        ("INT253", "Linux Administration Lab"),
        ("INT354", "Machine Learning Laboratory"),
        ("CSE339", "Computer Networks Laboratory"),
        ("INT306", "Database Management Systems Lab"),
    ],
    "ece": [
        ("ECE249", "Basic Electrical and Electronics Engineering"),
        ("ECE221", "Analog Circuits"),
        ("ECE312", "Digital Signal Processing"),
        ("ECE305", "Communication Systems"),
    ],
    "ece_lab": [
        ("ECE279", "Basic Electronics Laboratory"),
        ("ECE346", "Embedded Systems Laboratory"),
        ("ECE318", "Digital Design Laboratory"),
        ("ECE398", "VLSI Design Laboratory"),
    ],
    "gen": [
        ("MTH401", "Discrete Mathematics"),
        ("MTH174", "Engineering Mathematics"),
        ("PEV301", "Verbal Ability"),
        ("PEA306", "Analytical Skills-II"),
        ("CHE110", "Environmental Studies"),
    ],
    "lsb": [
        ("MGN231", "Principles of Management"),
        ("MKT301", "Marketing Management"),
        ("FIN303", "Corporate Finance"),
        ("OPR203", "Operations Management"),
    ],
}

TIMETABLE_SECTIONS = {
    "cse": SECTIONS["CSE"],
    "cse_lab": SECTIONS["CSE"],
    "ece": SECTIONS["ECE"],
    "ece_lab": SECTIONS["ECE"],
    "gen": SECTIONS["CSE"] + SECTIONS["ECE"] + SECTIONS["MEC"],
    "lsb": SECTIONS["LSB"],
}

TIMETABLE_FACULTY = {
    "cse": ["Dr. Neha Verma", "Dr. Amit Khanna", "Priya Nair", "Rohit Saini", "Dr. Kavita Arora", "Deepak Rana"],
    "cse_lab": ["Dr. Neha Verma", "Priya Nair", "Rohit Saini", "Deepak Rana", "Sneha Kulkarni"],
    "ece": ["Dr. Arjun Menon", "Ritu Chaudhary", "Naveen Reddy"],
    "ece_lab": ["Ritu Chaudhary", "Naveen Reddy", "Dr. Arjun Menon"],
    "gen": ["Dr. Suresh Pillai", "CDC Trainer · Verbal", "CDC Trainer · Aptitude", "Simran Gill"],
    "lsb": ["Nikhil Agarwal", "Dr. Swati Bedi"],
}

# ~20 rooms that carry the published timetable -> course pool
TIMETABLE_ROOMS = {
    "34-301": "cse",
    "34-302": "cse",
    "34-303": "cse",
    "34-304": "cse",
    "34-405": "cse",
    "32-201": "gen",
    "32-202": "gen",
    "33-205": "ece",
    "37-101": "lsb",
    "37-102": "lsb",
    "32-LT-1": "gen",
    "34-LT-1": "cse",
    "37-LT-1": "lsb",
    "34-LAB-1": "cse_lab",
    "34-LAB-2": "cse_lab",
    "34-LAB-3": "cse_lab",
    "38-LAB-1": "cse_lab",
    "38-LAB-2": "cse_lab",
    "33-LAB-1": "ece_lab",
    "33-LAB-2": "ece_lab",
    "33-LAB-3": "ece_lab",
}

# ── History shape ───────────────────────────────────────────────────────────

# Average bookings per resource per open day, before weekday/exam/heat factors.
TYPE_RATE = {
    "classroom": 1.3,
    "lecture-theatre": 0.5,
    "computer-lab": 1.8,
    "electronics-lab": 1.0,
    "seminar-hall": 0.5,
    "meeting-room": 1.8,
    "sports": 3.4,
    "equipment": 0.7,
    "vehicle": 0.25,
    "studio": 1.4,
}

# Per-resource demand multipliers: hot spots and expensive, rarely-used kit.
HEAT = {
    "38-LAB-2": 2.0,
    "SPT-BB-1": 1.6,
    "SPT-BB-2": 1.3,
    "34-SH-1": 1.4,
    "EQ-GPU-01": 1.6,
    "EQ-CAM-01": 1.4,
    "EQ-VR-01": 1.1,
    "SPT-GYM-1": 0.8,
    "EQ-SEM-01": 0.06,
    "EQ-3DP-02": 0.1,
    "EQ-OSC-02": 0.25,
    "33-LAB-4": 0.3,
    "18-AUD": 0.3,
    "18-CR-1": 0.5,
    "32-LT-2": 0.4,
    "VEH-BUS-5": 0.6,
}

# Denied-attempt pressure (unmet demand) concentrated on a few resources.
HOT_DEMAND = {"38-LAB-2": 2.2, "SPT-BB-1": 2.6, "SPT-BB-2": 1.6, "EQ-GPU-01": 1.2, "EQ-CAM-01": 0.8, "SPT-BD-1": 0.6}

# Hour-of-day weights by usage profile.
HOUR_PROFILES = {
    "day": {8: 1, 9: 2, 10: 3, 11: 5, 12: 5, 13: 4, 14: 5, 15: 5, 16: 4, 17: 3, 18: 2, 19: 1},
    "lab": {8: 1, 9: 2, 10: 3, 11: 4, 12: 4, 13: 4, 14: 5, 15: 5, 16: 5, 17: 5, 18: 4, 19: 3},
    "sports": {6: 3, 7: 3, 8: 1, 9: 1, 10: 1, 11: 1, 12: 1, 13: 1, 14: 1, 15: 2, 16: 4, 17: 6, 18: 7, 19: 7, 20: 5},
    "equipment": {9: 2, 10: 3, 11: 4, 12: 3, 13: 3, 14: 4, 15: 4, 16: 2},
    "vehicle": {6: 3, 7: 4, 8: 3, 9: 2, 10: 1, 14: 1},
    "studio": {9: 1, 10: 2, 11: 2, 12: 2, 13: 2, 14: 3, 15: 3, 16: 4, 17: 5, 18: 5, 19: 3},
}

TYPE_PROFILE = {
    "classroom": ("day", [60, 60, 60, 90, 120]),
    "lecture-theatre": ("day", [60, 90, 120, 180]),
    "computer-lab": ("lab", [60, 90, 120, 120, 180]),
    "electronics-lab": ("lab", [60, 120, 120, 180]),
    "seminar-hall": ("day", [120, 120, 180, 180, 240, 300]),
    "meeting-room": ("day", [30, 60, 60, 60, 90]),
    "sports": ("sports", [60, 60, 60, 120]),
    "equipment": ("equipment", [60, 120, 120, 180, 240]),
    "vehicle": ("vehicle", [240, 360, 480, 600]),
    "studio": ("studio", [60, 90, 120, 120, 180]),
}

# Who books each type: (role pool, weight)
BOOKERS = {
    "classroom": [("faculty", 5), ("student", 4), ("staff", 1)],
    "lecture-theatre": [("faculty", 7), ("staff", 2), ("dept_head", 1)],
    "computer-lab": [("student", 6), ("faculty", 4)],
    "electronics-lab": [("student", 6), ("faculty", 4)],
    "seminar-hall": [("faculty", 6), ("staff", 3), ("dept_head", 1)],
    "meeting-room": [("student", 6), ("faculty", 3), ("dept_head", 1)],
    "sports": [("student", 9), ("staff", 1)],
    "equipment": [("student", 7), ("faculty", 3)],
    "vehicle": [("faculty", 5), ("staff", 4), ("dept_head", 1)],
    "studio": [("student", 8), ("faculty", 2)],
}

TOPICS = [
    "Generative AI in practice",
    "Cloud-native architectures",
    "Careers in VLSI",
    "Startup funding 101",
    "Design thinking for engineers",
    "Threat hunting on Linux",
    "Sustainable manufacturing",
    "Financial modelling with Python",
    "Open-source contribution",
    "Research writing & ethics",
]
CLUBS = [
    "Coding Club",
    "Robotics Society",
    "Photography Club",
    "Music Society",
    "Entrepreneurship Cell",
    "Drama Club",
    "NSS Unit",
    "Basketball Squad",
    "Badminton Club",
    "Design Collective",
    "Literary Society",
    "Google Developer Student Club",
]
TEAMS = ["Byte Busters", "Null Pointers", "Team Phoenix", "Stack Smashers", "Quantum Leap", "Team Nimbus"]

TITLES = {
    "classroom": [
        "Make-up class · {course}",
        "Doubt-clearing session · {course}",
        "Group study · {course}",
        "{club} weekly meet",
        "Mock viva practice · {course}",
        "Remedial class · {course}",
    ],
    "lecture-theatre": [
        "Guest lecture · {topic}",
        "Combined class · {course}",
        "Orientation · {section}",
        "Mock test · {course}",
        "Placement aptitude session",
    ],
    "computer-lab": [
        "Extra practice · {course}",
        "Capstone project work",
        "Hackathon prep · {team}",
        "Mock placement coding test",
        "Lab re-test · {course}",
        "Kaggle study group",
    ],
    "electronics-lab": [
        "Circuit debugging · {course}",
        "Capstone hardware build",
        "Robotics Society build night",
        "Lab re-test · {course}",
        "PCB soldering practice",
    ],
    "seminar-hall": [
        "Guest lecture · {topic}",
        "Department colloquium",
        "Workshop · {topic}",
        "Pre-placement talk",
        "{club} inauguration",
        "Research seminar · {topic}",
    ],
    "meeting-room": [
        "Project sync · {team}",
        "Capstone review with mentor",
        "{club} core-team meeting",
        "Interview practice panel",
        "Section coordination · {section}",
        "Thesis discussion",
    ],
    "sports": [
        "Pickup game",
        "Practice · inter-hostel league",
        "Team practice · {club}",
        "Friendly match · {section}",
        "Fitness session",
        "Tournament warm-up",
    ],
    "vehicle": [
        "Industrial visit · {section}",
        "Team travel · inter-university meet",
        "Field trip · {course}",
        "Guest pick-up · Jalandhar railway station",
        "NSS village outreach camp",
    ],
    "studio": [
        "Band rehearsal · {club}",
        "Podcast recording · {club}",
        "Studio session · {course}",
        "Portfolio work · {course}",
        "Jury prep · {course}",
    ],
}

EQUIPMENT_TITLES = {
    "dslr-camera": ["Shoot for DES205 assignment", "Event coverage · {club}", "Portfolio shoot", "Documentary footage"],
    "projector": ["Outdoor screening · {club}", "Hostel movie night", "Club demo day"],
    "3d-printer": ["Prototype print · capstone", "Enclosure print · {team}", "Gear set print · MEC project"],
    "oscilloscope": ["Signal debugging · {course}", "Capstone board bring-up", "Lab measurement · {course}"],
    "vr-headset": ["VR usability study", "XR coursework demo", "Unity build testing"],
    "drone": ["Aerial survey · campus mapping", "Event aerials · {club}"],
    "microscope": ["Fracture surface imaging", "Coating thickness study", "Research sample imaging"],
    "gpu-server": ["Model training run · {team}", "LLM fine-tuning experiment", "Thesis experiments"],
}

REJECTION_REASONS = [
    "The hall is already committed to the department orientation that day.",
    "Please route this through your faculty coordinator.",
    "This kit is reserved for the DES205 jury that week.",
    "We can't staff an evening event of this size — try a weekday afternoon.",
    "Driver roster is full that day; please pick another date.",
    "Needs an induction first — book the 30-minute session with the custodian.",
]

CANCEL_REASONS = [
    "Cancelled by requester",
    "Class rescheduled",
    "Plans changed",
    "Team couldn't make it",
    "Moved to an online session",
]

# ── Inventory ───────────────────────────────────────────────────────────────

# sku, name, kind, unit, resource code, type code, total, available, reorder, max_per_booking, description
INVENTORY = [
    ("ACC-HDMI-01", "HDMI & USB-C adapter kit", "accessory", "kits", None, "classroom", 20, 17, 4, 2,
     "HDMI, USB-C and mini-DisplayPort adapters in a pouch."),
    ("ACC-MIC-01", "Wireless handheld microphone", "accessory", "pcs", None, "seminar-hall", 12, 10, 3, 4,
     "UHF handheld mic with spare AA batteries."),
    ("ACC-COAT-01", "Lab coat (M/L/XL)", "accessory", "pcs", None, "electronics-lab", 40, 34, 8, 6,
     "Cotton lab coats; return to the custodian's desk."),
    ("ACC-PROBE-01", "Oscilloscope probe set (10×)", "accessory", "sets", None, "electronics-lab", 24, 6, 6, 4,
     "Passive 10× probes with ground springs."),
    ("ACC-BREAD-01", "Breadboard & jumper kit", "accessory", "kits", None, "electronics-lab", 30, 22, 6, 4,
     "Full-size breadboard with a jumper wire set."),
    ("ACC-TRIPOD-01", "Fluid-head video tripod", "accessory", "pcs", "EQ-CAM-01", None, 3, 3, 1, 1,
     "Aluminium tripod with fluid head and quick-release plate."),
    ("ACC-BATT-A7", "Spare camera battery (NP-FZ100)", "accessory", "pcs", "EQ-CAM-01", None, 4, 1, 2, 2,
     "Charged spares for the Sony kit."),
    ("ACC-BATT-R6", "Spare camera battery (LP-E6NH)", "accessory", "pcs", "EQ-CAM-02", None, 4, 3, 1, 2,
     "Charged spares for the Canon kit."),
    ("ACC-DRN-BAT", "Drone intelligent flight battery", "accessory", "pcs", "EQ-DRN-01", None, 4, 4, 1, 3,
     "Extra flight batteries (~40 min each)."),
    ("ACC-BBALL-01", "Basketball (size 7)", "accessory", "pcs", None, "sports", 16, 12, 4, 3,
     "Composite leather match balls, from the equipment desk."),
    ("ACC-RACQ-01", "Badminton racquet pair", "accessory", "pairs", None, "sports", 20, 16, 4, 2,
     "Graphite racquets, issued in pairs."),
    ("ACC-FBALL-01", "Football (size 5)", "accessory", "pcs", None, "sports", 10, 9, 2, 2,
     "Match footballs."),
    ("CON-SHUTTLE-01", "Shuttlecock tube (nylon, 6)", "consumable", "tubes", None, "sports", 30, 4, 6, 2,
     "Nylon shuttles; tubes are not returned."),
    ("CON-PLA-01", "PLA filament spool (1 kg)", "consumable", "spools", "EQ-3DP-01", None, 12, 3, 5, 1,
     "1.75 mm PLA, assorted colours."),
    ("CON-RESIN-01", "Standard resin cartridge (1 L)", "consumable", "cartridges", "EQ-3DP-02", None, 6, 5, 2, 1,
     "Grey standard resin for the SLA printer."),
    ("CON-MARKER-01", "Whiteboard marker set", "consumable", "sets", None, "classroom", 80, 46, 20, 2,
     "Four-colour marker set with a duster."),
    ("CON-PAPER-01", "A4 printer paper ream", "consumable", "reams", None, "computer-lab", 40, 18, 10, 2,
     "500-sheet reams for the lab printer."),
    ("CON-SANI-01", "Hand sanitiser (500 ml)", "consumable", "bottles", None, "meeting-room", 24, 2, 4, 1,
     "Pump bottle for shared rooms."),
    ("CON-VRCOVER-01", "VR face cover (disposable)", "consumable", "pcs", "EQ-VR-01", None, 100, 38, 20, 4,
     "Single-use hygienic covers for the headset."),
]  # fmt: skip

# ── Maintenance ─────────────────────────────────────────────────────────────

# Past windows, relative to today: (resource code, days ago, start "HH:MM", hours, title, kind, vendor, status)
# Placed on Sundays/evenings or on rooms without classes so they never collide with the timetable.
PAST_MAINTENANCE = [
    ("34-LAB-1", 33, "17:30", 3, "PC re-imaging for the new term", "upgrade", "LPU IT Services", "completed"),
    ("38-LAB-2", 26, "17:00", 4, "GPU driver & CUDA 12 upgrade", "upgrade", "LPU IT Services", "completed"),
    (
        "33-LAB-2",
        19,
        "17:00",
        3,
        "Spectrum analyser calibration",
        "calibration",
        "Keysight authorised service",
        "completed",
    ),
    ("SPT-BB-1", 16, "06:00", 4, "Court resurfacing touch-up", "repair", "Sportina Surfaces, Jalandhar", "completed"),
    ("EQ-3DP-01", 12, "09:00", 3, "Nozzle and belt replacement", "repair", "", "completed"),
    (
        "18-AUD",
        9,
        "09:00",
        6,
        "Sound system tuning before tech fest",
        "preventive",
        "Acoustic Labs, Ludhiana",
        "completed",
    ),
    ("34-LT-1", 5, "17:00", 2, "Lecture-capture camera firmware", "upgrade", "LPU IT Services", "completed"),
    ("SPT-GYM-1", 4, "06:00", 3, "Treadmill servicing", "preventive", "FitTech Services", "completed"),
    ("37-MR-1", 22, "17:00", 2, "Conferencing codec replacement", "repair", "", "cancelled"),
    ("EQ-SEM-01", 14, "09:00", 4, "Annual vacuum-pump service", "preventive", "Zeiss India service", "cancelled"),
]

# Future windows: (resource code, days ahead, start, hours, title, kind, vendor, displace_a_booking)
FUTURE_MAINTENANCE = [
    ("34-LAB-1", "next-sat", "14:00", 4, "Quarterly PC re-imaging", "upgrade", "LPU IT Services", True),
    ("33-LAB-2", 6, "17:00", 2, "Oscilloscope probe calibration", "calibration", "Keysight authorised service", False),
    (
        "EQ-3DP-02",
        8,
        "09:00",
        4,
        "Resin tank replacement & levelling",
        "preventive",
        "Formlabs partner, Chandigarh",
        False,
    ),
    ("18-AUD", 12, "08:00", 8, "Stage lighting rig inspection", "preventive", "Acoustic Labs, Ludhiana", False),
    ("SPT-FB-1", 4, "06:00", 6, "Pitch rest & re-seeding", "preventive", "", False),
]

# Open breakdown reports: (resource code, reporter username, severity, summary, details, acknowledged)
BREAKDOWNS = [
    ("34-303", "student", "low", "Projector image flickers on the HDMI input",
     "Works fine on VGA. Flicker starts after about 10 minutes.", False),
    ("38-LAB-2", "faculty", "high", "Workstation 17: GPU fan grinding, machine shuts down under load",
     "Students moved to WS-18. Thermal shutdown during PyTorch training.", True),
    ("SPT-BB-1", "s014", "low", "Net torn on the north hoop", "", False),
    ("SPT-BD-3", "s022", "critical", "Roof leak — water pooling on the court surface",
     "Leak above the service door after last night's rain; surface is slippery.", False),
]  # fmt: skip

# Resolved reports in the past: (resource code, days ago, reporter username, severity, summary, resolution)
RESOLVED_BREAKDOWNS = [
    ("34-302", 18, "faculty", "high", "Air conditioner not cooling", "Gas top-up and filter clean by estate team."),
    ("EQ-CAM-01", 11, "s031", "low", "Lens cap missing from the kit", "Replacement cap added to the kit."),
    ("SPT-BD-2", 7, "s045", "high", "Two floor-mat seams lifting", "Mat re-taped and rolled."),
]

# ── Personas' extras ────────────────────────────────────────────────────────

SAVED_RESOURCES = {"student": ["38-LAB-2", "38-MR-1", "SPT-BB-1"], "faculty": ["34-LAB-2", "34-SH-1", "34-LT-1"]}

# Background students who miss check-ins more often (still capped below the restriction tier).
FLAKY_STUDENTS = ["s009", "s017", "s033", "s058", "s071", "s104"]

# Student whose booking is left un-checked-in 20 minutes past its start, for the live no-show demo.
NO_SHOW_DEMO_STUDENT = "s007"
