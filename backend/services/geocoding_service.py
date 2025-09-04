import os
import aiohttp
import urllib.parse
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class GeocodingService:
    """Service for geocoding addresses using Google Maps API"""
    
    def __init__(self):
        # Get API key from environment variable
        self.api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        self.geocoding_url = "https://maps.googleapis.com/maps/api/geocode/json"
        self.maps_base_url = "https://www.google.com/maps/search/?api=1"
        
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_API_KEY not found in environment variables")
    
    async def geocode_address(self, address: str) -> Optional[Dict]:
        """
        Geocode an address to get coordinates and Google Maps URL
        
        Args:
            address: Full address string to geocode
            
        Returns:
            Dictionary with lat, lng, maps_url, and formatted_address or None if failed
        """
        if not self.api_key:
            logger.error("Cannot geocode without Google Maps API key")
            # Return a fallback response
            return {
                'lat': None,
                'lng': None,
                'maps_url': self._generate_maps_url_from_address(address),
                'formatted_address': address,
                'status': 'no_api_key'
            }
        
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'address': address,
                    'key': self.api_key,
                    'language': 'es'  # Spanish results
                }
                
                async with session.get(self.geocoding_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data['status'] == 'OK' and data['results']:
                            result = data['results'][0]
                            location = result['geometry']['location']
                            
                            return {
                                'lat': location['lat'],
                                'lng': location['lng'],
                                'formatted_address': result['formatted_address'],
                                'maps_url': self._generate_maps_url(location['lat'], location['lng'], address),
                                'place_id': result.get('place_id'),
                                'status': 'ok'
                            }
                        elif data['status'] == 'ZERO_RESULTS':
                            logger.warning(f"No results found for address: {address}")
                            return {
                                'lat': None,
                                'lng': None,
                                'maps_url': self._generate_maps_url_from_address(address),
                                'formatted_address': address,
                                'status': 'zero_results'
                            }
                        else:
                            logger.error(f"Geocoding API error: {data['status']}")
                            return None
                    else:
                        logger.error(f"Geocoding API HTTP error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error geocoding address: {str(e)}")
            # Return fallback with just the maps URL
            return {
                'lat': None,
                'lng': None,
                'maps_url': self._generate_maps_url_from_address(address),
                'formatted_address': address,
                'status': 'error'
            }
    
    def _generate_maps_url(self, lat: float, lng: float, address: str) -> str:
        """Generate Google Maps URL from coordinates"""
        # Use coordinates for more accurate location
        query = f"{lat},{lng}"
        params = {'query': query}
        return f"{self.maps_base_url}&{urllib.parse.urlencode(params)}"
    
    def _generate_maps_url_from_address(self, address: str) -> str:
        """Generate Google Maps URL from address only (fallback)"""
        params = {'query': address}
        return f"{self.maps_base_url}&{urllib.parse.urlencode(params)}"
    
    async def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict]:
        """
        Reverse geocode coordinates to get address
        
        Args:
            lat: Latitude
            lng: Longitude
            
        Returns:
            Dictionary with address information or None if failed
        """
        if not self.api_key:
            logger.error("Cannot reverse geocode without Google Maps API key")
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'latlng': f"{lat},{lng}",
                    'key': self.api_key,
                    'language': 'es'
                }
                
                async with session.get(self.geocoding_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data['status'] == 'OK' and data['results']:
                            result = data['results'][0]
                            
                            # Parse address components
                            components = {}
                            for component in result['address_components']:
                                types = component['types']
                                if 'street_number' in types:
                                    components['numero'] = component['long_name']
                                elif 'route' in types:
                                    components['calle'] = component['long_name']
                                elif 'neighborhood' in types or 'sublocality' in types:
                                    components['colonia'] = component['long_name']
                                elif 'locality' in types:
                                    components['ciudad'] = component['long_name']
                                elif 'administrative_area_level_1' in types:
                                    components['estado'] = component['long_name']
                                elif 'country' in types:
                                    components['pais'] = component['long_name']
                                elif 'postal_code' in types:
                                    components['codigo_postal'] = component['long_name']
                            
                            return {
                                'formatted_address': result['formatted_address'],
                                'components': components,
                                'place_id': result.get('place_id')
                            }
                        else:
                            logger.warning(f"No results for reverse geocoding: {lat}, {lng}")
                            return None
                    else:
                        logger.error(f"Reverse geocoding API HTTP error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error reverse geocoding: {str(e)}")
            return None
    
    async def validate_address(self, address_data: Dict) -> Dict:
        """
        Validate and standardize an address
        
        Args:
            address_data: Dictionary with address components
            
        Returns:
            Dictionary with validation results and standardized address
        """
        # Build address string from components
        address_parts = []
        
        if address_data.get('calle') and address_data.get('numero'):
            address_parts.append(f"{address_data['calle']} {address_data['numero']}")
        
        if address_data.get('colonia'):
            address_parts.append(address_data['colonia'])
        
        if address_data.get('ciudad'):
            address_parts.append(address_data['ciudad'])
        
        if address_data.get('estado'):
            address_parts.append(address_data['estado'])
        
        if address_data.get('codigo_postal'):
            address_parts.append(f"C.P. {address_data['codigo_postal']}")
        
        if address_data.get('pais'):
            address_parts.append(address_data['pais'])
        
        full_address = ", ".join(address_parts)
        
        # Geocode to validate
        result = await self.geocode_address(full_address)
        
        if result and result.get('status') == 'ok':
            return {
                'valid': True,
                'formatted_address': result['formatted_address'],
                'lat': result['lat'],
                'lng': result['lng'],
                'maps_url': result['maps_url'],
                'confidence': 'high'
            }
        elif result and result.get('status') == 'zero_results':
            return {
                'valid': False,
                'formatted_address': full_address,
                'lat': None,
                'lng': None,
                'maps_url': result['maps_url'],
                'confidence': 'low',
                'message': 'No se pudo verificar la dirección exacta'
            }
        else:
            return {
                'valid': False,
                'formatted_address': full_address,
                'lat': None,
                'lng': None,
                'maps_url': self._generate_maps_url_from_address(full_address),
                'confidence': 'none',
                'message': 'Error al validar la dirección'
            }
    
    def get_static_map_url(self, lat: float, lng: float, zoom: int = 15, size: str = "400x300") -> str:
        """
        Generate URL for static map image
        
        Args:
            lat: Latitude
            lng: Longitude
            zoom: Zoom level (1-20)
            size: Image size (e.g., "400x300")
            
        Returns:
            URL for static map image
        """
        if not self.api_key:
            return ""
        
        base_url = "https://maps.googleapis.com/maps/api/staticmap"
        params = {
            'center': f"{lat},{lng}",
            'zoom': zoom,
            'size': size,
            'markers': f"color:red|{lat},{lng}",
            'key': self.api_key,
            'language': 'es'
        }
        
        return f"{base_url}?{urllib.parse.urlencode(params)}"
    
    def get_embed_map_url(self, address: str = None, lat: float = None, lng: float = None) -> str:
        """
        Generate URL for embedded map iframe
        
        Args:
            address: Address string
            lat: Latitude (optional if address provided)
            lng: Longitude (optional if address provided)
            
        Returns:
            URL for embedded map
        """
        if not self.api_key:
            return ""
        
        base_url = "https://www.google.com/maps/embed/v1/place"
        
        if lat and lng:
            # Use coordinates
            q = f"{lat},{lng}"
        elif address:
            # Use address
            q = address
        else:
            return ""
        
        params = {
            'key': self.api_key,
            'q': q,
            'language': 'es',
            'zoom': '15'
        }
        
        return f"{base_url}?{urllib.parse.urlencode(params)}"
    
    @staticmethod
    def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calculate distance between two points in kilometers using Haversine formula
        
        Args:
            lat1, lng1: First point coordinates
            lat2, lng2: Second point coordinates
            
        Returns:
            Distance in kilometers
        """
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in kilometers
        
        # Convert to radians
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c
        
        return round(distance, 2)