from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse, JsonResponse
import csv
from .forms import SearchForm
from .models import Lead
from .utils import GooglePlacesScraper

def homepage(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'homepage.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('homepage')

@login_required
def dashboard(request):
    form = SearchForm()
    recent_leads = Lead.objects.all().order_by('-created_at')[:10]
    total_leads = Lead.objects.count()
    
    # Check API key status
    api_key = settings.GOOGLE_PLACES_API_KEY
    api_status = "not_configured"
    api_message = ""
    
    if api_key:
        scraper = GooglePlacesScraper(api_key)
        if scraper.test_api_connection():
            api_status = "working"
            api_message = "API key is working"
        else:
            api_status = "error"
            api_message = "API key is not working. Please check your configuration."
    else:
        api_message = "API key not found. Please add GOOGLE_PLACES_API_KEY to your .env file."
    
    return render(request, 'dashboard.html', {
        'form': form,
        'recent_leads': recent_leads,
        'total_leads': total_leads,
        'api_status': api_status,
        'api_message': api_message
    })

@login_required
def search_results(request):
    if request.method == 'POST':
        form = SearchForm(request.POST)
        if form.is_valid():
            try:
                # Get form data
                keyword = form.cleaned_data['keyword']
                city = form.cleaned_data['city']
                country = form.cleaned_data['country']
                max_results = form.cleaned_data['max_results']
                only_with_phone = form.cleaned_data['only_with_phone']
                only_without_website = form.cleaned_data['only_without_website']
                try_find_email = form.cleaned_data['try_find_email']
                
                # Check if API key is configured
                if not settings.GOOGLE_PLACES_API_KEY:
                    messages.error(request, 'Google Places API key is not configured. Please add it to your .env file.')
                    return redirect('dashboard')
                
                # Initialize scraper
                scraper = GooglePlacesScraper(settings.GOOGLE_PLACES_API_KEY)
                
                # Test API connection first
                if not scraper.test_api_connection():
                    messages.error(request, 'Google Places API key is invalid or not working. Please check your API key and ensure Places API is enabled in Google Cloud Console.')
                    return redirect('dashboard')
                
                # Perform search
                leads, message = scraper.search_and_save(
                    keyword, city, country, max_results,
                    only_with_phone, only_without_website, try_find_email
                )
                
                # Check if there was an error in the message
                if message.startswith('ERROR:'):
                    messages.error(request, message.replace('ERROR:', '').strip())
                    return redirect('dashboard')
                
                # Calculate stats
                leads_with_phone = sum(1 for lead in leads if lead.phone)
                leads_with_website = sum(1 for lead in leads if lead.website)
                leads_with_email = sum(1 for lead in leads if lead.email)
                
                if leads:
                    messages.success(request, message)
                else:
                    messages.warning(request, message)
                
                return render(request, 'results.html', {
                    'leads': leads,
                    'keyword': keyword,
                    'city': city,
                    'country': country,
                    'only_with_phone': only_with_phone,
                    'only_without_website': only_without_website,
                    'try_find_email': try_find_email,
                    'leads_with_phone': leads_with_phone,
                    'leads_with_website': leads_with_website,
                    'leads_with_email': leads_with_email,
                    'total_results': len(leads)
                })
                
            except Exception as e:
                messages.error(request, f'An error occurred: {str(e)}')
                return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the errors in the form.')
            return redirect('dashboard')
    else:
        return redirect('dashboard')

@login_required
def export_csv(request):
    # Create HttpResponse with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="leads.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    writer.writerow(['Name', 'Phone', 'Email', 'Website', 'Address', 'City', 'Country', 'Rating', 'Date Added'])
    
    # Write leads to CSV
    leads = Lead.objects.all().order_by('-created_at')
    for lead in leads:
        writer.writerow([
            lead.name,
            lead.phone or '',
            lead.email or '',
            lead.website or '',
            lead.address,
            lead.city,
            lead.country,
            lead.rating or '',
            lead.created_at.strftime('%Y-%m-%d %H:%M')
        ])
    
    return response

@login_required
def clear_leads(request):
    if request.method == 'POST':
        count = Lead.objects.count()
        Lead.objects.all().delete()
        messages.success(request, f'Successfully cleared {count} lead(s)')
    return redirect('dashboard')

@login_required
def test_api(request):
    """Test endpoint to verify API connectivity"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    api_key = settings.GOOGLE_PLACES_API_KEY
    if not api_key:
        return JsonResponse({'error': 'API key not configured'}, status=500)
    
    scraper = GooglePlacesScraper(api_key)
    
    # Test API connection
    api_working = scraper.test_api_connection()
    
    # Test geocoding
    lat, lng, address = None, None, None
    geocoding_success = False
    if api_working:
        lat, lng, address = scraper.geocode_location('London', 'United Kingdom')
        geocoding_success = bool(lat and lng)
    
    # Test places search
    places = []
    places_success = False
    if geocoding_success:
        places = scraper.search_places('restaurant', lat, lng, max_results=3)
        places_success = len(places) > 0
    
    # Test place details
    details_success = False
    if places_success and len(places) > 0:
        details = scraper.get_place_details(places[0]['place_id'])
        details_success = bool(details)
    
    return JsonResponse({
        'api_key_configured': bool(api_key),
        'api_key_preview': api_key[:10] + '...' if api_key else None,
        'api_connection_test': {
            'success': api_working,
            'message': 'API connection successful' if api_working else 'API connection failed'
        },
        'geocoding_test': {
            'success': geocoding_success,
            'lat': lat,
            'lng': lng,
            'address': address,
            'message': f"Successfully geocoded London, UK" if geocoding_success else "Geocoding failed"
        },
        'places_search_test': {
            'success': places_success,
            'count': len(places),
            'sample': [{'name': p.get('name'), 'place_id': p.get('place_id')} for p in places[:2]] if places else [],
            'message': f"Found {len(places)} restaurants" if places_success else "No places found"
        },
        'place_details_test': {
            'success': details_success,
            'message': 'Successfully retrieved place details' if details_success else 'Failed to get place details'
        }
    })

@login_required
def debug_api(request):
    """Detailed API debug view"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    api_key = settings.GOOGLE_PLACES_API_KEY
    if not api_key:
        return JsonResponse({'error': 'API key not configured'}, status=500)
    
    scraper = GooglePlacesScraper(api_key)
    debug_info = scraper.debug_api_setup()
    
    # Test with a real location the user might use
    test_locations = [
        {'city': 'New York', 'country': 'USA'},
        {'city': 'London', 'country': 'UK'},
        {'city': 'Paris', 'country': 'France'},
        {'city': 'Tokyo', 'country': 'Japan'},
    ]
    
    location_tests = []
    for loc in test_locations:
        lat, lng, address = scraper.geocode_location(loc['city'], loc['country'])
        location_tests.append({
            'input': f"{loc['city']}, {loc['country']}",
            'success': bool(lat and lng),
            'lat': lat,
            'lng': lng,
            'address': address
        })
    
    debug_info['location_tests'] = location_tests
    
    return JsonResponse(debug_info)