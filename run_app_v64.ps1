Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& "$PSScriptRoot\venv-64\Scripts\Activate.ps1"
python -m streamlit run src/app/main.py --server.port 8502 --server.address 0.0.0.0
