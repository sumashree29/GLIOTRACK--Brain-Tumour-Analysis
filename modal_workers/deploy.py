"""
Deploy the Modal segmentation worker.
Run: python modal_workers/deploy.py
"""
import subprocess, sys

def main():
    print("Deploying Modal segmentation worker...")
    subprocess.run(
        [sys.executable, "-m", "modal", "deploy",
         "modal_workers/segmentation_worker.py"],
        check=True,
    )
    print("Deployment complete.")
    print("Copy the webhook URL into MODAL_WEBHOOK_URL in your .env")

if __name__ == "__main__":
    main()
