# Fluffy Engine - Automated Sales Scraper

Welcome to **fluffy-engine** - an automated sales data scraper that runs on GitHub Actions!

## 🎯 What This Does

- ✅ Scrapes sales data from https://std.nest.net.np
- ✅ Uploads data to Google Sheets automatically
- ✅ Takes screenshots and saves to Google Drive
- ✅ Runs every 6 hours completely free
- ✅ No server maintenance required

## 🚀 Features

- **Automated Scheduling**: Runs every 6 hours via GitHub Actions
- **Duplicate Prevention**: Never adds the same sale twice
- **Error Handling**: Robust error handling and logging
- **Screenshot Backup**: Daily screenshots saved to Google Drive
- **Free Operation**: Uses GitHub's free 2000 minutes/month

## 📊 Your Configuration

- **Google Sheet**: [Your Sales Data Sheet](https://docs.google.com/spreadsheets/d/1E7rx09A7fBZCk3MsbxQ1dZgqWyvZFd95hRRpd9v6uSM)
- **Google Drive**: [Screenshot Folder](https://drive.google.com/drive/folders/1RV38tg98YiUPUuTLEipYI4KKegNXcibw)
- **Schedule**: Every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)

## 🔧 How It Works

1. **GitHub Actions** triggers the workflow on schedule
2. **Chrome browser** (headless) opens the target website
3. **Selenium** extracts sales data from the page
4. **Google Sheets API** updates your spreadsheet
5. **Google Drive API** uploads screenshot for backup
6. **Duplicate check** ensures no repeated entries

## 📈 Monitoring

- Check the **Actions** tab to see run history
- Green checkmark = successful run
- Red X = something went wrong (check logs)
- Manual trigger available anytime

## 🛠️ Tech Stack

- **Python 3.10+**
- **Selenium WebDriver**
- **Google Sheets API**
- **Google Drive API**
- **GitHub Actions**

## 📝 Repository Structure

```
fluffy-engine/
├── chatgptversionscraper_github.py  # Main scraper script
├── requirements.txt                 # Python dependencies
├── .github/workflows/scraper.yml    # GitHub Actions workflow
├── .env.template                    # Environment variables template
└── README.md                        # This file
```

## 🎉 Status

Repository: **https://github.com/exswooning/fluffy-engine**
Status: **Running automatically every 6 hours**
Last Updated: **2025-09-13 09:15:00 UTC**

---

*Powered by GitHub Actions - Because automation is awesome! 🤖*
