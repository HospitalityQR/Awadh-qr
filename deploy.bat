@echo off
echo ========================================================
echo   AWADH FINE DINE RESTAURANT - LUXURY QR ^& STANDEE DEPLOYER
echo ========================================================
echo.
echo [1/3] Generating 300 DPI Standees, Assets ^& QR Codes...
python generate_qr.py
echo.
echo [2/3] Staging and Committing Changes...
git add .
git commit -m "Update Awadh Fine Dine Luxury QR & Standees"
echo.
echo [3/3] Pushing to GitHub Pages (main)...
git push
echo.
echo [DONE] Live changes deployed successfully!
pause
