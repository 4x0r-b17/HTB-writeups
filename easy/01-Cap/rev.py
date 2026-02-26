import requests
def get_data(ip_address, id_param):
    # Construct the URL
    url = f"http://{ip_address}/data/{id_param}"
    
    try:
        # Make GET request
        response = requests.get(url, timeout=10)
        
        # Raise error for bad status codes (4xx, 5xx)
        response.raise_for_status()
        
        # Print response content
        print("Status Code:", response.status_code)
        print("ID:", response.text)
        
        return response.text

    except requests.exceptions.RequestException as e:
        print("HTTP Request failed:", e)
        return None


# Example usage
if __name__ == "__main__":
    ip = "10.129.3.111"
    data_id = 123
    

    for id in range(0, 1000):    
        res = get_data(ip, id)
        with open(f"{id}.txt", 'w') as f:
            f.write(res)

