
import os
import random
import pandas as pd
import numpy as np

def generate():
    random.seed(42)
    np.random.seed(42)

    departments = ['Computer Science (CSE)', 'Information Technology (IT)', 'Artificial Intelligence (AI-DS)', 'Electronics (ECE)']
    designations = [
        ('Professor', 14, 0.25),
        ('Associate Professor', 16, 0.35),
        ('Assistant Professor', 18, 0.40)
    ]

    first_names = [
        'Rajesh', 'Ananya', 'Amit', 'Priya', 'Suresh', 'Sneha', 'Vikram', 'Pooja',
        'Rohan', 'Neha', 'Arun', 'Kavita', 'Manish', 'Deepa', 'Sanjay', 'Ritu',
        'Gaurav', 'Swati', 'Kunal', 'Divya', 'Naveen', 'Meera', 'Alok', 'Shalini'
    ]
    last_names = [
        'Sharma', 'Iyer', 'Verma', 'Nair', 'Patel', 'Deshmukh', 'Gupta', 'Menon',
        'Joshi', 'Choudhury', 'Kulkarni', 'Bose', 'Reddy', 'Singhal', 'Mishra', 'Rao'
    ]

    rows = []
    for i in range(1, 401):
        fac_id = f"FAC_{i:03d}"
        name = f"Dr. {random.choice(first_names)} {random.choice(last_names)}"
        dept = random.choice(departments)
        
        desig_tuple = random.choices(designations, weights=[d[2] for d in designations])[0]
        desig = desig_tuple[0]
        max_limit = desig_tuple[1]

        scenario = random.choices(['underload', 'balanced', 'overload'], weights=[0.25, 0.50, 0.25])[0]

        if scenario == 'underload':
            target_hours = random.randint(6, 11)
        elif scenario == 'balanced':
            target_hours = random.randint(12, max_limit)
        else:
            target_hours = random.randint(max_limit + 1, max_limit + 9)

        if desig == 'Professor':
            teaching = int(target_hours * random.uniform(0.35, 0.50))
            lab = int(target_hours * random.uniform(0.05, 0.15))
            admin = int(target_hours * random.uniform(0.20, 0.35))
            research = target_hours - (teaching + lab + admin)
        elif desig == 'Associate Professor':
            teaching = int(target_hours * random.uniform(0.40, 0.55))
            lab = int(target_hours * random.uniform(0.15, 0.25))
            admin = int(target_hours * random.uniform(0.10, 0.20))
            research = target_hours - (teaching + lab + admin)
        else:
            teaching = int(target_hours * random.uniform(0.50, 0.65))
            lab = int(target_hours * random.uniform(0.20, 0.35))
            admin = int(target_hours * random.uniform(0.00, 0.10))
            research = target_hours - (teaching + lab + admin)

        teaching = max(2, teaching)
        lab = max(0, lab)
        admin = max(0, admin)
        research = max(0, research)
        total_hours = teaching + lab + admin + research

        unique_courses = min(4, max(1, int(np.ceil(teaching / 4.0))))
        days_taught = min(6, max(3, int(np.ceil((teaching + lab) / 3.5))))

        if total_hours < 12:
            stress_level = 0
            stress_label = 'Underloaded'
        elif total_hours <= max_limit:
            stress_level = 1
            stress_label = 'Balanced'
        else:
            stress_level = 2
            stress_label = 'Overloaded'

        rows.append({
            'FacultyID': fac_id,
            'Name': name,
            'Department': dept,
            'Designation': desig,
            'TeachingHours': teaching,
            'LabHours': lab,
            'AdminHours': admin,
            'ResearchHours': research,
            'TotalHours': total_hours,
            'MaxPermissibleHours': max_limit,
            'UniqueCourses': unique_courses,
            'DaysTaught': days_taught,
            'WorkloadRatio': round(total_hours / max_limit, 2),
            'StressLevel': stress_level,
            'StressLabel': stress_label
        })

    df = pd.DataFrame(rows)
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(curr_dir, 'faculty_workload.csv')
    df.to_csv(out_path, index=False)
    print(f"[SUCCESS] Generated {len(df)} faculty records at: {out_path}")
    print("\nTarget Distribution:")
    print(df['StressLabel'].value_counts())

if __name__ == '__main__':
    generate()
