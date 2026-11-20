
import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

def train():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(base_dir)
    data_path = os.path.join(project_dir, 'dataset', 'faculty_workload.csv')

    print(f"[INFO] Loading dataset from: {data_path}")
    df = pd.read_csv(data_path)
    print(f"[INFO] Dataset shape: {df.shape}")

    num_features = ['TeachingHours', 'LabHours', 'AdminHours', 'ResearchHours', 'UniqueCourses', 'DaysTaught']
    cat_features = ['Designation']
    target = 'StressLevel'

    X = df[num_features + cat_features]
    y = df[target]

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), num_features),
            ('cat', OneHotEncoder(drop='first', sparse_output=False, handle_unknown='ignore'), cat_features)
        ]
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    candidate_models = {
        'Random Forest': RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42),
        'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42),
        'Decision Tree': DecisionTreeClassifier(max_depth=5, random_state=42),
        'Gaussian Naive Bayes': GaussianNB()
    }

    results = {}
    fitted_pipelines = {}
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    for name, clf in candidate_models.items():
        pipe = Pipeline([
            ('preprocessor', preprocessor),
            ('classifier', clf)
        ])
        pipe.fit(X_train, y_train)
        fitted_pipelines[name] = pipe

        y_pred = pipe.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, average='weighted', zero_division=0)
        rec = recall_score(y_test, y_pred, average='weighted', zero_division=0)
        f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
        cv_scores = cross_val_score(pipe, X, y, cv=cv, scoring='accuracy')

        cm = confusion_matrix(y_test, y_pred).tolist()

        results[name] = {
            'accuracy': round(float(acc) * 100, 2),
            'precision': round(float(prec) * 100, 2),
            'recall': round(float(rec) * 100, 2),
            'f1_score': round(float(f1) * 100, 2),
            'cv_mean': round(float(cv_scores.mean()) * 100, 2),
            'cv_std': round(float(cv_scores.std()) * 100, 2),
            'confusion_matrix': cm
        }
        print(f"  > {name:20} -> Accuracy: {acc*100:.2f}% | F1: {f1*100:.2f}% | 5-Fold CV: {cv_scores.mean()*100:.2f}%")

    primary_pipe = fitted_pipelines['Logistic Regression']
    model_path = os.path.join(base_dir, 'workload_model.joblib')
    joblib.dump(primary_pipe, model_path)
    print(f"[SUCCESS] Exported primary model to: {model_path}")

    clf = primary_pipe.named_steps['classifier']
    cat_encoder = primary_pipe.named_steps['preprocessor'].named_transformers_['cat']
    feature_names = num_features + list(cat_encoder.get_feature_names_out(cat_features))
    avg_weights = np.mean(np.abs(clf.coef_), axis=0)
    total_w = np.sum(avg_weights)

    feature_rankings = []
    for f_name, w in zip(feature_names, avg_weights):
        feature_rankings.append({
            'feature': f_name,
            'importance_score': round(float(w), 4),
            'importance_percentage': round(float((w / total_w) * 100), 1)
        })
    feature_rankings.sort(key=lambda x: x['importance_score'], reverse=True)

    metadata = {
        'model_name': 'Chronos Workload Stress Classifier',
        'algorithm': 'Logistic Regression Multi-Class Classifier',
        'accuracy': results['Logistic Regression']['accuracy'],
        'classes': ['Underloaded', 'Balanced', 'Overloaded'],
        'dataset_summary': {
            'total_faculty': int(df.shape[0]),
            'departments_count': int(df['Department'].nunique()),
            'distribution': {
                'underloaded': int((y == 0).sum()),
                'balanced': int((y == 1).sum()),
                'overloaded': int((y == 2).sum())
            }
        },
        'benchmarks': results,
        'feature_importance': feature_rankings,
        'academic_guidelines': {
            'Assistant Professor': {'max_hours': 18, 'ideal_range': '14-18 hrs/week'},
            'Associate Professor': {'max_hours': 16, 'ideal_range': '12-16 hrs/week'},
            'Professor': {'max_hours': 14, 'ideal_range': '10-14 hrs/week'}
        }
    }

    meta_path = os.path.join(base_dir, 'model_metadata.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    print(f"[SUCCESS] Exported metadata to: {meta_path}")

if __name__ == '__main__':
    train()
