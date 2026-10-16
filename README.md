# Incumbent Clock!

**Who holds Ann Arbor's city contracts, how they won them, and when they end.**

When a city contract ends, other companies get a chance to compete for it. From my research, for a company that sells to government, the end date of a government contract is an extremely important fact, and it's usually deep in long council memos that most people aren't gonna read. "Incumbent Clock" reads every Ann Arbor City Council resolution since July 2022 and pulls out each contract's vendor, amount, award method (bid, cooperative or sole source) and end date. This website is a visualization tool for the data and links you back to where the information came from. 

This was built almost entirely with AI tools. I did extensive research, understood the problem, understood the technicals and made sure I knew what was going on, and built a lot of accounting for why I think visualization tools like this aren't as popular. I think there are a couple of reasons? But one of them is absolutely trust. Like say hallucination when you have a simple agent crawl through a bunch of pdfs, and it makes data up about something. One thing I did in response to this, I took inspiration from a blogger I like to read from, where when you hover over a data point, it shows you the page with the quote of where that the information comes from, and a snippet of what it is. I thought it'd be pretty useful for a tool like this so you know the information isn't just made up. Another thing I did was set the rule that a fact only counts if its quote appears word for word in the record. And you can check yourself by just clicking on the fact, and it takes you to the Legislar page with the information!

I think this is pretty cool, and would totally be helpful for me as a salesperson/company that looks for government contracts and needs information on what's going on. 

## How to run it

You need Python 3.9 or newer. There's nothing else to install, because the data is already included.

```
git clone https://github.com/syedak1/pursuit.git
cd pursuit
python3 -m clock serve

python3 -m clock refresh
```

then open local host **http://localhost:8000** in your browser. You can also just open `web/index.html` directly.

You could start on the **For Pursuit** tab, it has a mini tour of the tool.

### optional

Download the latest records from Ann Arbor and rebuild, which might take a little:

```
python3 -m clock refresh
```

to run the given tests:

```
pip install pytest
python3 -m pytest -q
```
just to make sure the info parts of the tool are actually working right

## What's on the site

- **For Pursuit:** A guided tour of the site with baked in examples.
- **Where to sell:** What the information for a company would basically look like. You see the contracts in that market ending in the next 18 months, who holds them, upcoming council votes, and the departments that buy from that area. 
- **Timeline:** One bar per vendor, from first award to last known end date. Competitors you pick are highlighted.
- **Competition:** how much of the city's contracting was competitively bid, and who keeps winning without competition.
- **Research:** Search and filter every record, including the full memo text.
- **How it works:** the method, the limits and a glossary.

Point at any underlined fact to see the exact sentence it came from. Click the fact itself to keep that preview open.

## How it works

1. **Download.** Get every council resolution since July 2022 from Legistar's public API. Legistar is the system Ann Arbor uses to publish council records.
2. **Read.** Text patterns pull facts from each title and staff memo: vendor, amount, award method, term, end date, renewal options and memo author.
3. **Check.** A fact is kept only if its quote appears word for word in the record.
4. **Calculate.** End dates, totals and contract history are worked out in code.
5. **Show.** The website is built from the result.

## The provided data

- 1,814 council resolutions from July 2022 to October 2026.
- 677 of them are approved vendor contracts, worth about $521M as approved by council.
- 157 of the 318 service contracts have an end date the tool could find.

## Limits

- Ann Arbor only, and only purchases over $75,000. Smaller purchases don't go to council.
- About half of service contracts have no end date found yet. The contracts attached as PDFs aren't read yet.
- Amounts are what council approved, not what was actually paid.

## With another week

- I'd probably make this a working database with more information
- Read the attached contract PDFs, and run an optional AI step on memos the patterns missed. Then measure accuracy against 40 hand-checked records.
- Add more cities? Expand the scope?
- I'd definitely need more information to use/compare against so I know what I'm doing is actually accurate. Like I could maybe add the city's payment data (A2OpenBook) to compare approved against paid.
- Something like email alerts when a contract in someones market is coming up could be useful?
- I'd definitely look more into how local governments contract with medical companies. I currently don't know much about that, but it seems like there are things that could definitely use improvement (physical therapy, substance abuse treatment, emergency medical care, public health clinics!!).

## Project Folder layout

- `clock/`: the Python program that downloads, reads and checks the records.
- `web/`: the website.
- `data/`: the downloaded records and the database built from them.
- `tests/`: automatic checks, most based on real mistakes found in Ann Arbor's records.

