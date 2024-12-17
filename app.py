from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from pymongo import MongoClient
import datetime
"""
This app is an online management system for a pharmacy

The input and outputs varies based on what feature is being used

The orders page takes in order information as input and outputs a list of orders

The Inventory page takes in a search term as input and outputs a list of drugs in the inventory

The restock page takes in restock information and outputs a list of purchases.

The app is ran by executing app.py and opening the appropriate URL

"""

uri = "mongodb+srv://oliverren3:Fiv2Eep4rugvMvpe@cluster0.7udjt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
myclient = MongoClient(uri, server_api=ServerApi('1'))
mydb = myclient["db"]
ordercollection = mydb["orders"]
inventory_collection = mydb["inventory"]
suppliers_collection = mydb["suppliers"]
purchases_collection = mydb["purchases"] 
finance_collection = mydb["finance"]

#this method gets the inventory contents from the system's servers and returns it as a list of tuples
def get_inventory():
    inv_list = []
    collection = mydb["inventory"]
    #loops through inventory collection, and adds every document to the list as a tuple containing relevent data
    for post in collection.find():
        inv_list.append((post["name"], post["ID"], post["amount"]))

    return inv_list

#this method removes any items from the given list that don't contain the searched string
#in their name or as their ID
def inventory_search(items, search):

    #if item list is None raise exception
    if items == None:
        raise Exception("error: Item is None") 
    
    #if an item in the item list has an abnormal number of elements, raise exception
    for i in items:
        if len(i) != 3:
             raise Exception("error: Invalid item in list")

    #if no search term is entered, return the list unchanged
    if search == None:
        return items
    to_pop = []
    #loops through all elements of the list and keeps track of which indexes should be removed
    for i in range (len(items) - 1, -1, -1):
        #ignores capitalization when determining if name contains search term
        if items[i][0].upper().find(search.upper()) == -1 and items[i][1] != search:
            to_pop.append(i)
    #pops all items that dont match with search term
    for i in to_pop:
        items.pop(i)
    #returns array
    return items

app = Flask(__name__)
app.secret_key = 'flask'

orders = []

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_input = request.form['user_input']
        return render_template('index.html', user_input=user_input)
    return render_template('index.html', user_input=None)

@app.route('/inventory', methods=['GET', 'POST'])
def inventory_page():
    #get the inventory contents from backend server
    items = get_inventory()
    if request.method == 'POST':
        #get user input for search term
        user_input = request.form['user_input']
        #filter items using search term
        items = inventory_search(items, user_input)
        return render_template('inventory.html', user_input=user_input, items = items)
        
    return render_template('inventory.html', user_input=None, items = items)

@app.route('/restock', methods=['GET', 'POST'])
def restock():
    # get items from the db
    items = {item['name'].lower(): item['wholesale_price/unit'] for item in inventory_collection.find()}
    suppliers = {supplier['name']: (supplier['delivery_days'], supplier['delivery_cost']) for supplier in suppliers_collection.find()}
    purchases = list(purchases_collection.find())
    
    drug_name = None
    supplier = None
    quantity = None
    
    
    if request.method == 'POST':
        drug_name = request.form.get('drugName')  
        supplier = request.form.get('supplier')
        quantity = int(request.form.get('quantity'))

        if not drug_name or not quantity or not supplier:
            return jsonify({"error": "Missing fields"}), 400
       
        # get the item amount and add on the quantity restocked
        current_item = inventory_collection.find_one({"name": drug_name})

        if current_item is None:
            return jsonify({"error": "Item not found"}), 404  # Item not found
        
        # ensure quantity is a valid integer
        if not isinstance(quantity, int) or quantity < 0:
            return jsonify({"error": "Invalid quantity"}), 400  # Bad request for invalid quantity

        # check if the supplier exists
        if supplier not in suppliers:
            return jsonify({"error": "Supplier not found"}), 404  # Supplier not found


        # calculate the new qunatity to be updated in inventory
        new_quantity = current_item.get('amount', 0) + quantity 
        inventory_collection.update_one(
            {"name": drug_name},
            {"$set": {"amount": new_quantity}}
        )
        
        
        # get price info and calculate total price
        unit_price = current_item.get('wholesale_price/unit', 0)
        shipping_fee = suppliers[supplier][1]
        tax = 0.13
        total_price = float("{:.2f}".format(((unit_price * quantity) + shipping_fee) * (1 + tax)))
        
        # delivery and arrival days
        delivery_days = suppliers[supplier][0]
        arrival_date = (datetime.datetime.now() + datetime.timedelta(days=delivery_days)).strftime('%Y-%m-%d')
        
        # add to mongo db
        purchases_collection.insert_one({
            "drug_name": drug_name,
            "supplier": supplier,
            "quantity": str(quantity),
            "total_price": f"{total_price:.2f}",
            "arrival_date": arrival_date,
            "purchase_date": datetime.datetime.now()
        })
        
        
        # update mongo db finance collection
        finance = finance_collection.find_one()  
        new_balance = float("{:.2f}".format(finance['balance'] - total_price))
        finance_collection.update_one(
            {"_id": finance["_id"]},
            {"$set": {"balance": new_balance}}
        )
        
        # update the supplier's invoice_payments on mongo db
        suppliers_collection.update_one(
            {"name": supplier},
            {"$inc": {"invoice_payments": float("{:.2f}".format(total_price))}} 
        )
        
        # update purchases to the current mongo db collection before return
        purchases = list(purchases_collection.find())
        

        return render_template('restock.html', items=items, suppliers=suppliers, purchases=purchases, drugName=None, supplier=None, quantity=None)
        
        
    return render_template('restock.html', items=items, suppliers=suppliers, drugName=drug_name, supplier=supplier, quantity=quantity, purchases=purchases)

#Go to the orders page
@app.route('/orders', methods=['GET', 'POST'])
def orders_page():
    orders = list(ordercollection.find())
    return render_template('orders.html', orders=orders)

#Go to the new orders page
@app.route('/new_order', methods=['GET', 'POST'])
def new_order():
    if request.method == 'POST':
        # Get the form data
        customer = request.form['customer']
        items = request.form['items']
        location = request.form['location']
        cost = request.form['cost']
        amount = request.form['amount']
        new_order = {

            'order_id': f'#{ordercollection.count_documents({}) + 1:05d}', 

            'date': '10/25/2024',  
            'customer': customer,
            'location': location,
            'items': items,
            'amount': amount,
            'cost': "$"+cost
        }

        ordercollection.insert_one(new_order)
        orders = list(ordercollection.find())
        #Return to orders page
        flash("Order completed successfully!")
        return render_template('orders.html', orders = orders)

    return render_template('new_order.html')



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080) 
