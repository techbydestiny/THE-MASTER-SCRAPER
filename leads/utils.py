import requests
import time
import re
from django.conf import settings
from .models import Lead

class GooglePlacesScraper:
    def __init__(self, api_key):
        self.api_key = api_key
        self.geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
        self.places_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        self.details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        self.nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    
    def test_api_connection(self):
        """Test if API key is working with multiple endpoints"""
        
        # Test 1: Try a simple geocoding request
        test_params = {
            'address': 'London, UK',
            'key': self.api_key
        }
        
        try:
            response = requests.get(self.geocode_url, params=test_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'OK':
                    print("✅ API connection test passed (geocoding)")
                    return True
                elif data['status'] == 'REQUEST_DENIED':
                    print(f"❌ API key error: {data.get('error_message', 'Unknown')}")
                    return False
        except Exception as e:
            print(f"❌ API connection test failed: {e}")
        
        # Test 2: Try Places API as backup
        test_params = {
            'query': 'test',
            'key': self.api_key
        }
        
        try:
            response = requests.get(self.places_url, params=test_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data['status'] in ['OK', 'ZERO_RESULTS']:
                    print("✅ API connection test passed (places)")
                    return True
        except:
            pass
        
        return False
    def geocode_location(self, city, country):
        """Convert city and country to coordinates with better error handling"""
        address = f"{city}, {country}"
        print(f"Geocoding address: {address}")  # Debug log
        
        params = {
            'address': address,
            'key': self.api_key
        }
        
        try:
            response = requests.get(self.geocode_url, params=params, timeout=10)
            data = response.json()
            
            print(f"Geocoding response status: {data['status']}")  # Debug log
            
            if data['status'] == 'OK' and data.get('results'):
                location = data['results'][0]['geometry']['location']
                formatted_address = data['results'][0].get('formatted_address', '')
                print(f"Found coordinates: {location} for {formatted_address}")
                return location['lat'], location['lng'], formatted_address
            elif data['status'] == 'ZERO_RESULTS':
                print(f"No results found for {address}")
                return None, None, None
            elif data['status'] == 'REQUEST_DENIED':
                print(f"API key error: {data.get('error_message', 'Unknown error')}")
                return None, None, None
            else:
                print(f"Geocoding error: {data['status']}")
                return None, None, None
                
        except requests.exceptions.RequestException as e:
            print(f"Geocoding request failed: {e}")
            return None, None, None
        except ValueError as e:
            print(f"Geocoding JSON decode failed: {e}")
            return None, None, None
    
    def search_places(self, keyword, lat, lng, radius=50000, max_results=20):
        """Search for places using keyword and coordinates"""
        all_results = []
        next_page_token = None
        
        print(f"Searching for {keyword} near {lat}, {lng}")  # Debug log
        
        while len(all_results) < max_results:
            params = {
                'query': keyword,
                'location': f"{lat},{lng}",
                'radius': radius,
                'key': self.api_key
            }
            
            if next_page_token:
                params['pagetoken'] = next_page_token
                # Wait for token to become valid
                time.sleep(2)
            
            try:
                response = requests.get(self.places_url, params=params, timeout=10)
                data = response.json()
                
                print(f"Places API response status: {data['status']}")  # Debug log
                
                if data['status'] != 'OK':
                    if data['status'] == 'ZERO_RESULTS':
                        print("No results found")
                    else:
                        print(f"Places API error: {data.get('status')} - {data.get('error_message', '')}")
                    break
                
                # Add results
                if data.get('results'):
                    all_results.extend(data['results'])
                    print(f"Found {len(data['results'])} results, total so far: {len(all_results)}")
                
                # Check for next page
                next_page_token = data.get('next_page_token')
                if not next_page_token or len(all_results) >= max_results:
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"Places API request failed: {e}")
                break
            except ValueError as e:
                print(f"Places API JSON decode failed: {e}")
                break
        
        return all_results[:max_results]
    
    def get_place_details(self, place_id):
        """Get detailed information for a specific place"""
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_phone_number,international_phone_number,website,formatted_address,rating,user_ratings_total,price_level,opening_hours,types',
            'key': self.api_key
        }
        
        print(f"Getting details for place: {place_id}")  # Debug log
        
        try:
            response = requests.get(self.details_url, params=params, timeout=10)
            data = response.json()
            
            if data['status'] == 'OK':
                result = data.get('result', {})
                
                # Try both phone number formats
                phone = result.get('formatted_phone_number') or result.get('international_phone_number')
                
                details = {
                    'phone': phone,
                    'website': result.get('website'),
                    'address': result.get('formatted_address', ''),
                    'rating': result.get('rating'),
                    'user_ratings_total': result.get('user_ratings_total'),
                    'price_level': result.get('price_level'),
                    'types': result.get('types', [])
                }
                
                print(f"Found details - Phone: {bool(phone)}, Website: {bool(details['website'])}")  # Debug log
                return details
            else:
                print(f"Details API error for {place_id}: {data['status']}")
                return {}
                
        except Exception as e:
            print(f"Error getting place details: {e}")
            return {}
    
    def extract_email_from_website(self, website):
        """Simple email extraction from website - placeholder for now"""
        # This would require scraping the website - for MVP, return None
        # You could implement this later with BeautifulSoup
        return None
    
    def search_and_save(self, keyword, city, country, max_results, only_with_phone, only_without_website, try_find_email):
        """Main method to search and save leads"""
        
        # First, test API connection
        if not self.test_api_connection():
            return [], "ERROR: Google Places API key is invalid or not configured. Please check your API key in the .env file."
        
        # Get coordinates
        lat, lng, formatted_address = self.geocode_location(city, country)
        if not lat or not lng:
            return [], f"ERROR: Could not find coordinates for {city}, {country}. Please check the city and country names."
        
        # Search places
        places = self.search_places(keyword, lat, lng, max_results=max_results)
        if not places:
            return [], f"No businesses found for '{keyword}' in {city}, {country}. Try different keywords or location."
        
        leads_saved = []
        leads_skipped = 0
        leads_existing = 0
        
        for place in places:
            try:
                # Check if lead already exists
                if Lead.objects.filter(place_id=place['place_id']).exists():
                    leads_existing += 1
                    continue
                
                # Get details
                details = self.get_place_details(place['place_id'])
                
                # Apply filters
                if only_with_phone and not details.get('phone'):
                    leads_skipped += 1
                    continue
                if only_without_website and details.get('website'):
                    leads_skipped += 1
                    continue
                
                # Try to find email if requested
                email = None
                if try_find_email and details.get('website'):
                    email = self.extract_email_from_website(details['website'])
                
                # Create lead
                lead = Lead(
                    name=place.get('name', 'Unknown'),
                    phone=details.get('phone'),
                    email=email,
                    website=details.get('website'),
                    address=details.get('address', place.get('formatted_address', '')),
                    city=city,
                    country=country,
                    rating=details.get('rating'),
                    place_id=place['place_id']
                )
                lead.save()
                leads_saved.append(lead)
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Error processing place {place.get('place_id')}: {e}")
                continue
        
        # Create summary message
        summary = f"Found {len(leads_saved)} new leads"
        if leads_existing > 0:
            summary += f" ({leads_existing} already existed)"
        if leads_skipped > 0:
            summary += f" ({leads_skipped} filtered out)"
        
        return leads_saved, summary

def debug_api_setup(self):
    """Debug method to check API setup"""
    results = {
        'api_key_present': bool(self.api_key),
        'api_key_preview': self.api_key[:10] + '...' if self.api_key else None,
        'geocoding_api': {'working': False, 'message': ''},
        'places_api': {'working': False, 'message': ''},
        'details_api': {'working': False, 'message': ''}
    }
    
    # Test Geocoding API
    try:
        params = {
            'address': 'London, UK',
            'key': self.api_key
        }
        response = requests.get(self.geocode_url, params=params, timeout=5)
        data = response.json()
        results['geocoding_api']['working'] = data['status'] == 'OK'
        results['geocoding_api']['message'] = f"Status: {data['status']}"
    except Exception as e:
        results['geocoding_api']['message'] = str(e)
    
    # Test Places API
    try:
        params = {
            'query': 'restaurant in London',
            'key': self.api_key
        }
        response = requests.get(self.places_url, params=params, timeout=5)
        data = response.json()
        results['places_api']['working'] = data['status'] in ['OK', 'ZERO_RESULTS']
        results['places_api']['message'] = f"Status: {data['status']}"
    except Exception as e:
        results['places_api']['message'] = str(e)
    
    return results