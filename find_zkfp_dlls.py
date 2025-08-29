import os
import sys
import site

def find_pyzkfp_dlls():
    """Find all ZKFP2 DLL files in the pyzkfp package"""
    print("Searching for pyzkfp DLL files...")
    
    # Try different locations
    locations = []
    
    # Add site-packages paths
    locations.extend(site.getsitepackages())
    
    # Add user site-packages
    if hasattr(site, 'getusersitepackages'):
        locations.append(site.getusersitepackages())
    
    # Add current environment
    if 'VIRTUAL_ENV' in os.environ:
        locations.append(os.path.join(os.environ['VIRTUAL_ENV'], 'Lib', 'site-packages'))
    
    dll_files = []
    
    for location in locations:
        pyzkfp_path = os.path.join(location, 'pyzkfp')
        if os.path.exists(pyzkfp_path):
            print(f"Found pyzkfp at: {pyzkfp_path}")
            
            for root, dirs, files in os.walk(pyzkfp_path):
                for file in files:
                    if file.endswith(('.dll', '.so', '.dylib')):
                        full_path = os.path.join(root, file)
                        dll_files.append(full_path)
                        print(f"Found DLL: {file} at {full_path}")
    
    if not dll_files:
        print("No DLL files found! This might cause the libzkfpcsharp error.")
        print("Try installing pyzkfp with: pip install pyzkfp")
    else:
        print(f"\nTotal DLL files found: {len(dll_files)}")
        
        # Create a batch file to copy DLLs manually
        with open('copy_dlls.bat', 'w') as f:
            f.write('@echo off\n')
            f.write('echo Copying ZKFP2 DLL files...\n')
            for dll in dll_files:
                f.write(f'copy "{dll}" "dist\\" >nul 2>&1\n')
            f.write('echo DLL files copied to dist folder\n')
            f.write('pause\n')
        
        print("Created copy_dlls.bat to manually copy DLL files after build")
    
    return dll_files

if __name__ == "__main__":
    find_pyzkfp_dlls()
