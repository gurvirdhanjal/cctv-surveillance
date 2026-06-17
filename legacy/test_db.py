import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import os

print("="*60)
print("EMPLOYEE DATABASE DIAGNOSTIC")
print("="*60)

# Load database
try:
    employee_db = np.load("employee_db.npy", allow_pickle=True).item()
    print(f"✓ Database loaded successfully")
    print(f"✓ Number of employees: {len(employee_db)}")
except Exception as e:
    print(f"✗ ERROR loading database: {e}")
    exit(1)

print("\n" + "="*60)
print("CHECKING EACH EMPLOYEE'S EMBEDDING")
print("="*60)

# Check each employee's embedding
for emp_id, emb in employee_db.items():
    print(f"\nEmployee: {emp_id}")
    print(f"  - Type: {type(emb)}")
    print(f"  - Shape: {emb.shape if hasattr(emb, 'shape') else 'N/A'}")
    print(f"  - Dtype: {emb.dtype if hasattr(emb, 'dtype') else 'N/A'}")
    
    if hasattr(emb, 'shape'):
        print(f"  - Min value: {emb.min():.6f}")
        print(f"  - Max value: {emb.max():.6f}")
        print(f"  - Mean value: {emb.mean():.6f}")
        print(f"  - Std dev: {emb.std():.6f}")
        print(f"  - L2 norm: {np.linalg.norm(emb):.6f}")
        
        # Check for NaN or Inf
        if np.isnan(emb).any():
            print(f"  ⚠ WARNING: Contains NaN values!")
        if np.isinf(emb).any():
            print(f"  ⚠ WARNING: Contains Inf values!")
        
        # Check if all zeros
        if np.allclose(emb, 0):
            print(f"  ⚠ WARNING: All zeros!")
        
        # First 10 values
        print(f"  - First 10 values: {emb.flatten()[:10]}")

print("\n" + "="*60)
print("CROSS-COMPARISON BETWEEN EMPLOYEES")
print("="*60)

# Normalize all embeddings
employee_db_norm = {}
for emp_id, emb in employee_db.items():
    e = emb.astype(np.float32).reshape(1, -1)
    norm = np.linalg.norm(e)
    if norm > 1e-9:
        e = e / norm
    else:
        print(f"⚠ WARNING: {emp_id} has zero norm!")
    employee_db_norm[emp_id] = e

# Compare each pair
emp_list = list(employee_db_norm.keys())
print("\nCosine similarity matrix:")
print("(Should be ~1.0 on diagonal, <0.5 off-diagonal for different people)")
print()

# Header
print(f"{'':15}", end="")
for emp in emp_list:
    print(f"{emp[:12]:>12}", end="")
print()

# Matrix
for i, emp1 in enumerate(emp_list):
    print(f"{emp1[:15]:15}", end="")
    for j, emp2 in enumerate(emp_list):
        score = cosine_similarity(employee_db_norm[emp1], employee_db_norm[emp2])[0][0]
        print(f"{score:12.3f}", end="")
    print()

print("\n" + "="*60)
print("RECOMMENDATIONS")
print("="*60)

# Check if all embeddings are identical
all_identical = True
first_emb = None
for emp_id, emb in employee_db_norm.items():
    if first_emb is None:
        first_emb = emb
    else:
        if not np.allclose(emb, first_emb):
            all_identical = False
            break

if all_identical:
    print("🔴 CRITICAL: All embeddings are IDENTICAL!")
    print("   This means the database was created incorrectly.")
    print("   You need to regenerate employee_db.npy with actual face images.")
else:
    print("✓ Embeddings are different (good)")

# Check dimension
expected_dim = 512  # AdaFace IR50
actual_dims = [emb.shape[1] for emb in employee_db_norm.values()]
if all(d == expected_dim for d in actual_dims):
    print(f"✓ All embeddings have correct dimension ({expected_dim})")
else:
    print(f"🔴 CRITICAL: Embedding dimensions are wrong!")
    print(f"   Expected: {expected_dim}, Got: {actual_dims}")

print("\n" + "="*60)
print("HOW TO FIX")
print("="*60)
print("""
If embeddings are identical or incorrect:

1. You need to create employee_db.npy correctly using this script:
   
   # create_employee_db.py
   import cv2
   import numpy as np
   from face_utils import FaceRecognizerONNX
   import os
   
   recognizer = FaceRecognizerONNX(
       scrfd_onnx_path="models/scrfd_2.5g.onnx",
       adaface_onnx_path="models/adaface_ir50.onnx",
       conf_thres=0.5,
       min_face_size=30
   )
   
   employee_db = {}
   
   # Directory structure:
   # employees/
   #   ├── gurvir/
   #   │   ├── photo1.jpg
   #   │   ├── photo2.jpg
   #   ├── brijesh_sir/
   #   │   ├── photo1.jpg
   #   └── deepak/
   #       └── photo1.jpg
   
   employees_dir = "employees"
   
   for emp_name in os.listdir(employees_dir):
       emp_folder = os.path.join(employees_dir, emp_name)
       if not os.path.isdir(emp_folder):
           continue
       
       print(f"Processing {emp_name}...")
       
       embeddings = []
       for img_file in os.listdir(emp_folder):
           img_path = os.path.join(emp_folder, img_file)
           img = cv2.imread(img_path)
           
           if img is None:
               continue
           
           faces = recognizer.detect_and_extract(img)
           if len(faces) > 0:
               embeddings.append(faces[0]["embedding"])
               print(f"  ✓ {img_file}")
       
       if len(embeddings) > 0:
           # Average multiple photos
           avg_emb = np.mean(embeddings, axis=0)
           employee_db[emp_name] = avg_emb
           print(f"  ✓ {emp_name}: {len(embeddings)} photos averaged")
   
   np.save("employee_db.npy", employee_db)
   print(f"\\nSaved {len(employee_db)} employees to employee_db.npy")

2. Run: python create_employee_db.py

3. Then run this diagnosis script again to verify
""")