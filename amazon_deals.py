import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def get_products_from_deal(page, deal_link, custom_selector=None, scroll_wait_time=5):
    if not deal_link:
        return []
        
    def extract_price(element):
        price_selectors = [
            ".a-price .a-offscreen",
            ".a-price",
            "span.a-color-price",
            "span.a-color-base",
            ".a-size-base.a-color-price",
            "span.price",
            ".price"
        ]
        
        # 1. Standard CSS selectors inside element
        for sel in price_selectors:
            span = element.select_one(sel)
            if span:
                txt = span.get_text(strip=True)
                if txt and "$" in txt:
                    return txt
                    
        # 2. Check parents up to 6 levels (stopping at card boundaries to avoid bleeding into other cards)
        p = element.parent
        for _ in range(6):
            if not p or p.name in ["body", "html"]:
                break
            for sel in price_selectors:
                span = p.select_one(sel)
                if span:
                    txt = span.get_text(strip=True)
                    if txt and "$" in txt:
                        return txt
            # Stop traversing if we hit a standard Amazon product card container boundary
            if p.get("data-asin") or any(cls in p.get("class", []) for cls in ["s-result-item", "a-cardui", "s-card-container"]):
                break
            p = p.parent
            
        # 3. Regex match inside element text (supporting commas like $1,150.00)
        import re
        price_pattern = r"\$\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"
        match = re.search(price_pattern, element.get_text())
        if match:
            return match.group(0)
            
        # 4. Regex match in parent text up to 5 levels (stopping at card boundaries)
        p = element.parent
        for _ in range(5):
            if not p or p.name in ["body", "html"]:
                break
            match = re.search(price_pattern, p.get_text())
            if match:
                return match.group(0)
            if p.get("data-asin") or any(cls in p.get("class", []) for cls in ["s-result-item", "a-cardui", "s-card-container"]):
                break
            p = p.parent
            
        return "N/A"
    
    if custom_selector:
        # Auto-format selector: if user entered standard class name(s) like "a-link-normal"
        # or "a-section a-spacing-base", convert to standard CSS selector starting with a dot.
        custom_selector = custom_selector.strip()
        if not any(custom_selector.startswith(c) for c in [".", "#", "[", "*"]):
            standard_tags = {"a", "div", "li", "span", "img", "h1", "h2", "h3", "h4", "p", "button", "ul", "ol", "section"}
            first_word = custom_selector.split()[0].lower()
            if first_word not in standard_tags:
                words = custom_selector.split()
                custom_selector = "".join(f".{w}" if not w.startswith(".") else w for w in words)
        print(f"   [Resolved Selector] Using CSS query: '{custom_selector}'")

    print(f"-> Navigating to: {deal_link[:80]}...")
    try:
        # Navigate using the existing page (maintaining session/zip code context!)
        await page.goto(deal_link, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        
        products_dict = {}
        max_pages = 5
        current_page = 1
        
        while current_page <= max_pages:
            print(f"\n   [Page {current_page}] Starting incremental page scroll...")
            # Dynamic lazy loading: scroll incrementally and actively query DOM to ensure products render
            print("   [Paginator] Scrolling dynamically to render lazy-loaded products...")
            last_height = await page.evaluate("document.body.scrollHeight")
            for scroll_step in range(12):  # Scroll up to 12 steps
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(500)
                
                # Proactively inspect DOM content to see if dynamic product cards are rendered
                soup_check = BeautifulSoup(await page.content(), "html.parser")
                rendered_cards = soup_check.select('div[class*="productcard" i], div[class*="dealcard" i], [data-asin], [data-testid="deal-card"], div[class*="DealGridItem"], div[class*="DealItem"], .octopus-pc-item, a[class*="bxcGridOverlayLink"]')
                if len(rendered_cards) >= 8:
                    print(f"   [Paginator] Dynamic rendering detected: found {len(rendered_cards)} populated product cards in DOM.")
                    break
                    
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height and scroll_step > 4:
                    break
                last_height = new_height
                
            # Final wait for dynamic stabilization
            print(f"   Reached scroll limit. Waiting {scroll_wait_time} seconds for stabilization...")
            await page.wait_for_timeout(scroll_wait_time * 1000)
            
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            use_custom = bool(custom_selector)
            custom_elements = []
            
            if use_custom:
                # If the user provided a custom CSS selector
                print(f"   Searching for elements matching custom selector: '{custom_selector}'...")
                custom_elements = soup.select(custom_selector)
                
                # Dynamic hash suffix rescue!
                if not custom_elements:
                    import re
                    clean_words = []
                    for word in custom_selector.replace(".", " ").replace("#", " ").split():
                        cleaned = re.sub(r'_[A-Za-z0-9]{6,30}$', '', word)
                        # Filter out generic Amazon utility classes to prevent overly broad relaxed matches
                        if cleaned and len(cleaned) > 3 and cleaned.lower() not in ["a-color-base", "a-link-normal", "a-size-base", "a-truncate"]:
                            clean_words.append(cleaned)
                    
                    # Sort words by length in descending order to prioritize highly specific identifiers (e.g. productCardTitleLink)
                    clean_words = sorted(clean_words, key=len, reverse=True)
                    
                    for word in clean_words:
                        relaxed_sel = f'[class*="{word}"]'
                        elements = soup.select(relaxed_sel)
                        if elements:
                            print(f"   [Relaxed Match] Rescued {len(elements)} elements using relaxed selector '{relaxed_sel}'.")
                            custom_elements = elements
                            custom_selector = relaxed_sel  # Update selector for next pages
                            break
                            
                if not custom_elements:
                    print(f"   [Rescue] Custom selector '{custom_selector}' matched 0 elements.")
                    print("            Falling back to advanced automatic Event page parser...")
                    use_custom = False
                    
            if use_custom:
                print(f"   Found {len(custom_elements)} elements matching '{custom_selector}' on this page.")
                
                for el in custom_elements:
                    title = ""
                    link = ""
                    price = "N/A"
                    asin = el.get("data-asin", "N/A")
                    
                    # If the matched element itself is an anchor tag
                    if el.name == "a":
                        title = el.get_text(strip=True)
                        if not title:
                            img = el.find("img")
                            if img and img.get("alt"):
                                title = img.get("alt").strip()
                        link = el.get("href", "").strip()
                    else:
                        # If it's a container element, look for nested a tag
                        a_tag = el.find("a")
                        if a_tag:
                            title = a_tag.get_text(strip=True)
                            if not title:
                                img = a_tag.find("img")
                                if img and img.get("alt"):
                                    title = img.get("alt").strip()
                            link = a_tag.get("href", "").strip()
                            
                        # Also try looking for an h2/h3 inside container
                        h_tag = el.find(["h2", "h3", "h4"])
                        if h_tag:
                            title = h_tag.get_text(strip=True)
                            
                    # Fallback to element's own text if still no title
                    if not title:
                        title = el.get_text(" ", strip=True)[:100]
                        
                    # Normalize link first so we can parse title slug if empty
                    if link and link.startswith("/"):
                        link = "https://www.amazon.com" + link
                        
                    # Try parsing product title slug from URL if title is empty or generic
                    if not title or len(title) < 4:
                        if link and "/dp/" in link:
                            parts = link.split("/dp/")[0].split("/")
                            if parts:
                                slug = parts[-1].strip()
                                if slug and slug not in ["s", "gp", "product"]:
                                    title = slug.replace("-", " ").replace("_", " ").title()
                                    
                    if not title or len(title) < 2:
                        continue
                        
                    # Try finding price inside or around the element
                    price = extract_price(el)
                    
                    # Normalize link to a clean base URL for grouping & collapsing duplicate anchors
                    base_link = link
                    if base_link:
                        base_link = base_link.split("#")[0].split("?")[0]
                        if "/dp/" in base_link:
                            parts = base_link.split("/dp/")
                            base_link = parts[0] + "/dp/" + parts[1].split("/")[0]
                    
                    if not base_link:
                        base_link = title
                        
                    # Merge duplicate product parts (image, review, price anchors)
                    if base_link in products_dict:
                        existing = products_dict[base_link]
                        
                        # Decide if the new title is richer/better than the existing one
                        import re
                        is_existing_garbage = (
                            len(existing["title"]) < 5
                            or existing["title"].startswith("$")
                            or re.match(r"^\(?\d+(?:\.\d+)?\)?$", existing["title"])
                        )
                        is_new_garbage = (
                            len(title) < 5
                            or title.startswith("$")
                            or re.match(r"^\(?\d+(?:\.\d+)?\)?$", title)
                        )
                        
                        is_new_better = False
                        if is_existing_garbage and not is_new_garbage:
                            is_new_better = True
                        elif not is_existing_garbage and not is_new_garbage:
                            if len(title) > len(existing["title"]):
                                is_new_better = True
                                
                        if is_new_better:
                            existing["title"] = title
                            
                        # Update price if existing is N/A
                        if existing["price"] == "N/A" and price != "N/A":
                            existing["price"] = price
                        if existing["asin"] == "N/A" and asin != "N/A":
                            existing["asin"] = asin
                    else:
                        products_dict[base_link] = {
                            "asin": asin,
                            "title": title,
                            "price": price,
                            "link": link
                        }
            if not use_custom:
                product_elements = []
                if "/stores/" in deal_link:
                    print("   [Storefront] Detected Amazon Store page! Using Storefront DOM extraction...")
                    product_elements = soup.select('a[href*="/dp/"]')
                    print(f"   [Storefront] Found {len(product_elements)} product links in DOM.")
                else:
                    # Select all elements with data-asin (which are standard Amazon product cards)
                    for element in soup.find_all(attrs={"data-asin": True}):
                        asin = element.get("data-asin", "").strip()
                        if len(asin) == 10 and asin not in [p.get("asin") for p in products_dict.values()]:
                            product_elements.append(element)
                            
                    print(f"   Found {len(product_elements)} potential product container elements on this page.")
                
                # Event Fallback: compare standard products vs special Event layouts
                event_selectors = [
                    '[data-testid="deal-card"]',
                    'div[class*="DealGridItem"]',
                        'div[class*="DealItem"]',
                        '.octopus-pc-item',
                        'li[class*="octopus"]',
                        'a[class*="bxcGridOverlayLink"]',
                        '[role="listitem"]',
                        'div[class*="productcard" i]',
                        'div[class*="dealcard" i]',
                        '.s-result-item'
                    ]
                best_event_elements = []
                best_sel = ""
                for sel in event_selectors:
                    try:
                        elements = soup.select(sel)
                        if len(elements) > len(best_event_elements):
                            best_event_elements = elements
                            best_sel = sel
                    except Exception:
                        continue
                        
                if len(best_event_elements) > len(product_elements):
                    print(f"   [Event Fallback] Matching elements with selector '{best_sel}': {len(best_event_elements)} (Overrides standard {len(product_elements)} items)")
                    product_elements = best_event_elements
                if not product_elements:
                    print("   [Pagination] No product elements or fallbacks found on this page. Stopping pagination.")
                    break
                    
                for el in product_elements: # Scrape ALL products on the page as requested
                    title = ""
                    link = ""
                    price = ""
                    asin = el.get("data-asin", "").strip()
                    
                    # Direct check: if the matched element itself is an anchor link, initialize immediately!
                    if el.name == "a" and el.get("href"):
                        link = el.get("href").strip()
                        title = el.get("aria-label", "").strip() or el.get("title", "").strip() or el.get_text(strip=True)
                    
                    # Specialized parser for Amazon Event/Outlet Product Cards (case-insensitive)
                    event_card = None
                    for child in [el] + el.find_all(True):
                        classes = child.get("class", [])
                        testid = child.get("data-testid", "")
                        if "deal-card" in testid.lower() or any(c for c in classes if "productcard" in c.lower() or "dealcard" in c.lower() or "dealitem" in c.lower() or "octopus-pc-item" in c.lower()):
                            event_card = child
                            break
                        
                    if event_card:
                        # Find title inside the paragraph tag, title links, or dynamic spans
                        title_els = event_card.select('p, [class*="TitleLink"], [class*="title" i], [class*="Title"], span.a-truncate')
                        for title_el in title_els:
                            t = title_el.get_text(strip=True)
                            if t and len(t) > 5 and not any(kw in t.lower() for kw in ["off", "limited time", "deal of the day", "list price", "free delivery"]):
                                title = t
                                break
                            
                        # Find link
                        a_tag = event_card.select_one('a[class*="ContainingLink"], a[class*="TitleLink"], a[class*="link" i], a[class*="Link"]')
                        if not a_tag:
                            a_tag = event_card.find("a")
                        if a_tag and a_tag.get("href"):
                            link = a_tag.get("href").strip()
                            
                        # Find price inside the card
                        price = extract_price(event_card)
                    
                    # Standard fallback parser
                    if not title or not link:
                        # 1. Look for h2 or h3 header tag inside product card
                        h2_or_h3 = el.find(["h2", "h3"])
                        if h2_or_h3:
                            title = h2_or_h3.get_text(strip=True)
                        # 2. Look for nested image alt fallback
                        if not title:
                            img = el.find("img")
                            if img and img.get("alt"):
                                title = img.get("alt").strip()
                        # 3. Fallback to standard product title span classes or Event module titles
                        if not title:
                            title_spans = el.select("span.a-size-base-plus, span.a-size-medium, .a-size-mini a, [class*='productCard' i], [class*='ProductCard'], [class*='dealCard' i], [class*='DealCard'], span.a-truncate")
                            for title_span in title_spans:
                                t = title_span.get_text(strip=True)
                                if t and len(t) > 5 and not any(kw in t.lower() for kw in ["off", "limited time", "deal of the day", "list price", "free delivery"]):
                                    title = t
                                    break
                                
                        # 4. Final text search fallback for Event custom labels (filtering out promo labels)
                        if not title:
                            for p_tag in el.find_all(["p", "span"]):
                                t = p_tag.get_text(strip=True)
                                if (
                                    t 
                                    and len(t) > 10 
                                    and not t.startswith("$") 
                                    and not t.startswith("(") 
                                    and not any(kw in t.lower() for kw in ["off", "limited time", "deal of the day", "list price", "free delivery"])
                                ):
                                    title = t
                                    break
                                
                        # Find product page link
                        if not link:
                            a_tag = el.find("a", href=lambda h: h and ("/dp/" in h or "/gp/" in h or "/s?" in h or "/events/" in h))
                            if not a_tag:
                                a_tag = el.find("a")
                            if a_tag and a_tag.get("href"):
                                link = a_tag.get("href").strip()
                                
                            # Event fallback link extraction (hidden inside custom data attributes)
                            if not link:
                                link = el.get("data-a-href") or el.get("data-url") or ""
                                if not link:
                                    hidden_link_el = el.find(attrs={"data-a-href": True}) or el.find(attrs={"data-url": True})
                                    if hidden_link_el:
                                        link = hidden_link_el.get("data-a-href") or hidden_link_el.get("data-url") or ""
                                
                    if link and link.startswith("/"):
                        link = "https://www.amazon.com" + link
                        
                    # Extract ASIN from URL if not already found in data-asin
                    if (not asin or len(asin) != 10) and link:
                        if "/dp/" in link:
                            parts = link.split("/dp/")
                            if len(parts) > 1:
                                raw_asin = parts[1].split("/")[0].split("?")[0]
                                if len(raw_asin) == 10:
                                    asin = raw_asin
                                    
                    # Bulletproof Promo Filter: Clear infected titles before they collapse the dict
                    if title:
                        t_lower = title.lower()
                        if any(kw in t_lower for kw in ["off", "limited time", "deal of the day", "list price", "free delivery"]):
                            title = ""
                            
                    # Try parsing product title slug from URL if title is empty or generic
                    if not title or len(title) < 4:
                        if link and "/dp/" in link:
                            parts = link.split("/dp/")[0].split("/")
                            if parts:
                                slug = parts[-1].strip()
                                if slug and slug not in ["s", "gp", "product"]:
                                    title = slug.replace("-", " ").replace("_", " ").title()
                                    
                    # Ignore invalid, dummy, or accessibility helper anchor links
                    if not link or any(invalid in link.lower() for invalid in ["javascript:", "#skipped", "#main", "mailto:", "javascript;"]):
                        continue
                        
                    if not title or len(title) < 2:
                        continue
                        
                    # Extract image URL
                    image_url = None
                    img_tag = el.find("img")
                    if img_tag and img_tag.get("src"):
                        image_url = img_tag.get("src")

                    # Find price if not already set by specialized card parser
                    if not price:
                        price = extract_price(el)
                    
                    base_link = link
                    if base_link:
                        base_link = base_link.split("#")[0].split("?")[0]
                        if "/dp/" in base_link:
                            parts = base_link.split("/dp/")
                            base_link = parts[0] + "/dp/" + parts[1].split("/")[0]
                            
                    if not base_link:
                        base_link = title
                            
                    # Check for standard duplicates
                    if base_link not in products_dict:
                        products_dict[base_link] = {
                            "asin": asin if asin else "N/A",
                            "title": title,
                            "price": price,
                            "link": link,
                            "image": image_url
                        }
            
            # Check if there is a pagination button to go to the next page
            next_button_selectors = [
                "a.s-pagination-next",
                "li.a-last a",
                "a[aria-label*='next']",
                "a[class*='pagination-next']",
                "button[class*='pagination-next']",
                ".s-pagination-button[aria-label*='next']"
            ]
            
            found_next = False
            for sel in next_button_selectors:
                next_el = page.locator(sel).first
                if await next_el.is_visible() and await next_el.is_enabled():
                    print(f"   [Pagination] Found Next Page button matching selector '{sel}'. Clicking...")
                    # Scroll to next button to ensure it is clickable
                    await next_el.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)
                    await next_el.click()
                    await page.wait_for_timeout(4000)
                    current_page += 1
                    found_next = True
                    break
            
            if not found_next:
                print("   [Pagination] No visible/clickable 'Next Page' button found. Ending multi-page scraping.")
                break
                
        return list(products_dict.values())
    except Exception as e:
        print(f"   Error scraping products: {e}")
        return []

async def get_banner_deals(zip_code="41018"):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        page = await browser.new_page(
            viewport={"width": 1920, "height": 1080}
        )

        print("Opening Amazon homepage...")
        await page.goto("https://www.amazon.com", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        if zip_code:
            print(f"Setting zip code to {zip_code}...")
            is_modal_visible = await page.locator("#GLUXZipUpdateInput").is_visible()
            if not is_modal_visible:
                # Open location selector
                await page.locator("#nav-global-location-slot").click()
                await page.wait_for_timeout(2000)
                is_modal_visible = await page.locator("#GLUXZipUpdateInput").is_visible()

            if is_modal_visible:
                await page.locator("#GLUXZipUpdateInput").fill(zip_code)
                await page.wait_for_timeout(1000)
                
                # Click Apply
                await page.locator("#GLUXZipUpdate input").click()
                await page.wait_for_timeout(3000)
                
                # Dismiss the modal
                done_btn = page.locator("input[name='glowDoneButton']")
                confirm_close = page.locator("#GLUXConfirmClose").first
                
                if await done_btn.is_visible():
                    await done_btn.click()
                elif await confirm_close.is_visible():
                    await confirm_close.click()
                else:
                    await page.reload()
                
                await page.wait_for_timeout(4000)
                
                try:
                    location_text = await page.locator("#glow-ingress-line2").text_content()
                    print(f"Verified Location: {location_text.strip() if location_text else 'Unknown'}")
                except Exception:
                    pass
            else:
                print("Warning: Zip code selection input was not visible.")

        soup = BeautifulSoup(await page.content(), "html.parser")
        
        deals = {}

        # Main homepage hero carousel (matches both div and li elements)
        hero_sections = soup.select(".a-carousel-card")

        for section in hero_sections:
            title = ""
            
            # 1. Fallback to image alt text (highly common for hero banners on Amazon)
            img = section.find("img")
            if img and img.get("alt"):
                title = img.get("alt").strip()
            
            # 2. Fallback to text inside the card if image alt is not available
            if not title:
                texts = section.get_text("\n", strip=True).split("\n")
                cleaned = [t.strip() for t in texts if len(t.strip()) > 8]
                if cleaned:
                    title = " ".join(cleaned[:3])

            if title:
                # Exclude video player elements, dialog accessibility overlays, and Prime Video / streaming advertisements
                garbage_keywords = ["video player", "dialog window", "transparency", "prime video", "watch ", "stream"]
                if any(garbage in title.lower() for garbage in garbage_keywords):
                    continue
                
                # Remove garbage strings based on original logic
                if (
                    "amazon" not in title.lower()
                    or "off" in title.lower()
                    or "shop" in title.lower()
                ):
                    # Get link associated with the card
                    link = ""
                    a_tag = section.find("a")
                    if a_tag and a_tag.get("href"):
                        link = a_tag.get("href").strip()
                        if link.startswith("/"):
                            link = "https://www.amazon.com" + link
                    
                    deals[title] = link

        print("\n=== LIVE HERO BANNER DEALS (Zip: 41018) ===")
        deals_list = list(deals.items())
        for i, (deal, link) in enumerate(deals_list, 1):
            print(f"{i}. {deal}")

        # Check for command line argument or automatically scrape all deals
        import sys
        target_indices = []
        is_auto_run = False
        if len(sys.argv) > 1:
            arg = sys.argv[1].strip().lower()
            if arg == "all":
                target_indices = list(range(len(deals_list)))
                is_auto_run = True
            else:
                try:
                    idx = int(arg) - 1
                    if 0 <= idx < len(deals_list):
                        target_indices = [idx]
                        is_auto_run = True
                    else:
                        print(f"[-] Invalid deal number arg. Scraping all deals.")
                        target_indices = list(range(len(deals_list)))
                        is_auto_run = True
                except ValueError:
                    print(f"[-] Invalid arg '{arg}'. Scraping all deals.")
                    target_indices = list(range(len(deals_list)))
                    is_auto_run = True
        else:
            # Default to scraping all deals automatically so the user never has to input anything!
            print("\n   [Auto-Run] Scraping all deals automatically...")
            target_indices = list(range(len(deals_list)))
            is_auto_run = True

        for idx in target_indices:
            deal_title, deal_link = deals_list[idx]
            print("\n" + "="*60)
            
            if is_auto_run:
                choice_idx = idx
                custom_selector = None
                wait_time = 5
            else:
                user_choice = await asyncio.to_thread(
                    input, "Enter the deal number to scrape products (or 'q' to quit): "
                )
                user_choice = user_choice.strip().lower()
                
                if user_choice in ["q", "quit", "exit"]:
                    print("\nExiting and closing browser. Goodbye!")
                    break
                    
                try:
                    choice_idx = int(user_choice) - 1
                    if not (0 <= choice_idx < len(deals_list)):
                        print(f"[-] Invalid choice! Please enter a number between 1 and {len(deals_list)}.")
                        continue
                        
                    custom_selector = await asyncio.to_thread(
                        input, "Enter custom CSS selector/class (optional, e.g. '.a-cardui', or press Enter for default): "
                    )
                    custom_selector = custom_selector.strip()
                    if not custom_selector:
                        custom_selector = None
                        
                    wait_time_str = await asyncio.to_thread(
                        input, "Enter wait time (in seconds) after scrolling to bottom (optional, default: 5): "
                    )
                    wait_time = 5
                    if wait_time_str.strip():
                        try:
                            wait_time = int(wait_time_str.strip())
                        except ValueError:
                            print("   [Warning] Invalid wait time entered. Using default of 5 seconds.")
                except ValueError:
                    print("[-] Invalid input! Please enter a number or 'q'.")
                    continue
                    
            selected_deal, selected_link = deals_list[choice_idx]
            if selected_link:
                # Scrape products from this deal link with scrolling
                products = await get_products_from_deal(page, selected_link, custom_selector, scroll_wait_time=wait_time)
                if products:
                    print(f"\n[+] Scraped {len(products)} products in '{selected_deal}':")
                    for j, prod in enumerate(products, 1):
                        print(f"  {j}. {prod['title']}")
                        print(f"     Price: {prod['price']}")
                        print(f"     URL: {prod['link']}\n")
                else:
                    print("\n[-] No products found inside this deal link.")
            else:
                print("\n[-] No link available for this deal.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_banner_deals())