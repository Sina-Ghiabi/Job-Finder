<div align="center">

<img src="assets/banner.svg" alt="Job Finder" width="100%">

<br>

[![Stars](https://img.shields.io/github/stars/Sina-Ghiabi/Job-Finder?style=for-the-badge&logo=github&color=f5c542&labelColor=0b1020)](https://github.com/Sina-Ghiabi/Job-Finder/stargazers)
[![Platform](https://img.shields.io/badge/Windows-10%20%7C%2011-4f8cff?style=for-the-badge&logo=windows&logoColor=white&labelColor=0b1020)](#-before-you-start)
[![Python](https://img.shields.io/badge/Python-3.8%2B-22d3a6?style=for-the-badge&logo=python&logoColor=white&labelColor=0b1020)](#-quick-start)
[![Apify](https://img.shields.io/badge/Powered%20by-Apify-97d700?style=for-the-badge&labelColor=0b1020)](https://apify.com)
[![Claude](https://img.shields.io/badge/Screened%20by-Claude-d97757?style=for-the-badge&labelColor=0b1020)](https://www.anthropic.com)
[![License](https://img.shields.io/badge/License-PolyForm%20Strict-8b5cf6?style=for-the-badge&labelColor=0b1020)](LICENSE)

**Find jobs abroad without reading a thousand adverts yourself.**

[Why](#-why-this-exists) · [What it does](#-what-it-does) · [Before you start](#-before-you-start) · [Quick start](#-quick-start) · [Speed](#-speed) · [Docs](Document.md)

</div>

<br>

## 💛 Why this exists

Job Finder was built to make **finding work easier for Iranians living abroad** — people who need
roles that fit a visa, a language and a CV, and who cannot afford to scroll through thousands of
irrelevant listings to find the few that matter.

> **If it helps you, please give it a ⭐ — it is the only way other people find it.**

<div dir="rtl">

این برنامه برای ساده‌تر کردن پیدا کردن کار برای ایرانیان خارج از کشور ساخته شده است.
اگر به دردتان خورد، لطفاً یک ⭐ بدهید.

</div>

<br>

## ✨ What it does

You type a job title and pick countries. Job Finder asks the big job boards, throws away what you
could never take, and shows you the rest — scored against **your** résumé.

```mermaid
flowchart LR
    A["🔎 Search<br/>title · countries · type"] --> B["📥 Raw results<br/>nothing deleted yet"]
    B --> C["🧹 Filter<br/>rules + Claude"]
    C --> D["📊 Your table<br/>score · English? · sponsorship"]
    D --> E["📤 Excel · Applications tracker"]
```

| | |
|---|---|
| 🌍 **18 countries** | Italy, Germany, Netherlands, UK, France, Spain, Switzerland, Nordics, Canada, Australia, USA and more |
| 🎯 **Three kinds of search** | Jobs (Entry · Junior · Mid · Senior), **Internships**, and **Master's theses** — each in English first, then the country's own language |
| 🏠 **Remote or Any** | *Remote* asks every platform for remote work using each one's own parameter; *Any* keeps everything |
| 🗣️ **English? column** | Tick *English only* and nothing that demands another language shows up |
| 🤖 **Claude reads every advert** | Drops what you cannot do and scores the rest against your résumé — and **nothing is deleted without you seeing it** |
| 🛂 **Visa sponsorship** | A column for it, using public sponsor lists where they exist |
| 🗂️ **Applications tracker** | Remember what you applied to, and export everything to Excel |

<br>

## 🧰 Built with

| Part | What it uses |
|---|---|
| **Job boards** | [LinkedIn](https://apify.com/apimaestro/linkedin-jobs-scraper-api) · [Indeed](https://apify.com/valig/indeed-jobs-scraper) · [Glassdoor](https://apify.com/valig/glassdoor-jobs-scraper) through **Apify** actors |
| **Google** | [Apify Google Search](https://apify.com/apify/google-search-scraper) + a page crawler, for company career pages and local job boards |
| **Screening & scoring** | **Claude** (Anthropic API) |
| **Optional extras** | Jooble · Reed (UK) · France Travail · DeepL for translation |
| **App** | Python · **PySide6** (Qt) · pandas · openpyxl |

<br>

## 📋 Before you start

Get these ready first — the app asks for them on its first run:

- [ ] **An [Apify](https://apify.com) account and API token** — searches run as Apify actors, and you pay Apify per result
- [ ] **An [Anthropic](https://console.anthropic.com) API key**, with some credit — Claude screens and scores the listings
- [ ] **Your résumé** as a **PDF or Word (.docx)** file
- [ ] *Optional:* Jooble, Reed (UK), France Travail or DeepL keys for extra sources and translation
- [ ] **Windows 10 or 11**

> 💡 **Mind the cost.** Apify and Claude bill you directly. Use the **Results limit** dropdowns in the
> Search window (for example 50 rows) while you are trying things out.

<br>

## 🚀 Quick start

```bash
git clone https://github.com/Sina-Ghiabi/Job-Finder.git
cd Job-Finder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Then **New Search** → paste your keys and résumé → choose a title and countries → **Start Search**.
When it finishes, press **Filter**. Prefer a single `.exe`? See [Document.md](Document.md#building-the-exe).

<br>

## ⏱️ Speed

| Source | How long |
|---|---|
| LinkedIn · Indeed · Glassdoor | ⚡ **Fast** — the quick sources |
| **Google** | 🐢 **Much slower** — it searches the web and then opens each page. Untick it for a quick run and add it when you can wait |

<br>

## 📚 Documentation

The full, detailed manual — every rule, every column, and why each decision was made — is in
**[Document.md](Document.md)**.

<br>

## ⚖️ License

**Free to download and use for yourself — not to modify, redistribute or sell.**
Released under the [PolyForm Strict License 1.0.0](LICENSE): personal and other non-commercial use is
allowed; making changes, distributing copies, and any commercial use are not.

<br>

<div align="center">

**Made for Iranians abroad. If it helped you, ⭐ star the repo.**

</div>
