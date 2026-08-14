import mysql.connector
from datetime import datetime

class ExpenseTracker:

    def __init__(self):

        self.connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Raksha@511",
            database="expense_tracker"
        )

        self.cursor = self.connection.cursor()
        
# expense adding
#_________________________________________________________________________________________
    def add_expense(self):

        date_input = input("Enter date (DD-MM-YYYY): ")

        try:
            date = datetime.strptime(date_input, "%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError:
            print("Invalid date format! Please use DD-MM-YYYY.")
            return

        print("\nCategories:")
        print("1. Food")
        print("2. Travel")
        print("3. Shopping")
        print("4. Bills")
        print("5. Other")

        category_choice = input("Choose category: ")

        categories = {
            "1": "Food",
            "2": "Travel",
            "3": "Shopping",
            "4": "Bills",
            "5": "Other"
        }

        category = categories.get(category_choice)

        if category is None:
            print("Invalid category!")
            return

        amount = float(input("Enter amount: "))

        description = input("Enter description: ")

        query = """
        INSERT INTO expenses
        (expense_date, category, amount, description)
        VALUES (%s, %s, %s, %s)
        """

        values = (
            date,
            category,
            amount,
            description
        )

        self.cursor.execute(query, values)

        self.connection.commit()

        print("Expense added successfully!")

# expense editing
# _________________________________________________________________________________________
    def edit_expense(self):
        expense_id = int(input("Enter expense ID to edit: "))

        cursor = self.connection.cursor()

        # Check whether expense exists
        cursor.execute(
            "SELECT * FROM expenses WHERE id = %s",
            (expense_id,)
        )

        expense = cursor.fetchone()

        if expense is None:
            print("Expense not found!")
            cursor.close()
            return

        print("\nCurrent expense:")
        print(expense)

        print("Enter new category: ")
        print("\nCategories:")
        print("1. Food")
        print("2. Travel")
        print("3. Shopping")
        print("4. Bills")
        print("5. Other")

        category_choice = input("Choose category: ")

        categories = {
            "1": "Food",
            "2": "Travel",
            "3": "Shopping",
            "4": "Bills",
            "5": "Other"
        }

        category = categories.get(category_choice)

        if category is None:
            print("Invalid category!")
            return
        amount = float(input("Enter new amount: "))
        description = input("Enter new description: ")

        cursor.execute(
            """
            UPDATE expenses
            SET category = %s,
                amount = %s,
                description = %s
            WHERE id = %s
            """,
            (category, amount, description, expense_id)
        )

        self.connection.commit()

        print("Expense updated successfully!")

        cursor.close()

    # expense searching
    # _________________________________________________________________________________________
    def search_expense(self):
        print("\nSearch Expense Details")
        print("1. Through Category")
        print("2. Through ID")

        search_choice = input("Choose search choice: ")

        # Search by category
        if search_choice == "1":

            print("\nSearch through your categories:")
            print("1. Food")
            print("2. Travel")
            print("3. Shopping")
            print("4. Bills")
            print("5. Other")

            category_choice = input("Choose category: ")

            categories = {
                "1": "Food",
                "2": "Travel",
                "3": "Shopping",
                "4": "Bills",
                "5": "Other"
            }

            category = categories.get(category_choice)

            if category is None:
                print("Invalid category!")
                return

            cursor = self.connection.cursor()

            query = """
            SELECT id, expense_date, category, amount, description
            FROM expenses
            WHERE category = %s
            """

            cursor.execute(query, (category,))
            expenses = cursor.fetchall()

            if not expenses:
                print("No expenses found in this category!")
            else:
                print("\nExpenses")
                print("-" * 90)

                print(
                    f"{'ID':<5}"
                    f"{'Date':<15}"
                    f"{'Category':<15}"
                    f"{'Amount':<15}"
                    f"{'Description':<30}"
                )

                print("-" * 90)

                for expense in expenses:
                    print(
                        f"{expense[0]:<5}"
                        f"{str(expense[1]):<15}"
                        f"{expense[2]:<15}"
                        f"{str(expense[3]):<15}"
                        f"{expense[4]:<30}"
                    )

                print("-" * 90)
            cursor.close()

        # Search by ID

        elif search_choice == "2":

            expense_id = int(input("Enter expense ID to search: "))

            cursor = self.connection.cursor()

            query = """
            SELECT id, expense_date, category, amount, description
            FROM expenses
            WHERE id = %s
            """

            cursor.execute(query, (expense_id,))
            expense = cursor.fetchone()

            if expense is None:
                print("Expense not found!")
            else:
                print("\nExpense Details:")
                print("ID:", expense[0])
                print("Date:", expense[1])
                print("Category:", expense[2])
                print("Amount:", expense[3])
                print("Description:", expense[4])

            cursor.close()

        else:
            print("Invalid search choice!")

    # expense viewing
    # _________________________________________________________________________________________

    def view_expenses(self):

        query = """
        SELECT id, expense_date, category, amount, description
        FROM expenses
        ORDER BY expense_date DESC
        """

        self.cursor.execute(query)

        expenses = self.cursor.fetchall()

        if not expenses:
            print("No expenses found.")
            return

        print("\nYour Expenses")
        print("-" * 70)

        for number, expense in enumerate(expenses, start=1):
            print("No:", number)
            print("ID:", expense[0])
            print("Date:", expense[1])
            print("Category:", expense[2])
            print("Amount:", expense[3])
            print("Description:", expense[4])

            print("-" * 70)
    #expenses deletion
    #___________________________________________________________________________________
    def expense_deletion(self):
     expense_id = int(input("Enter expense ID to delete: "))

     cursor = self.connection.cursor()

     # Check whether expense exists
     cursor.execute(
        "SELECT * FROM expenses WHERE id = %s",
        (expense_id,)
     )

     expense = cursor.fetchone()

     if expense is None:
         print("Expense not found!")
         cursor.close()
         return

     print("\nExpense to be deleted:")
     print(expense)

     confirm = input("Are you sure you want to delete this expense? (yes/no): ")

     if confirm.lower() == "yes":

        query = """
        DELETE FROM expenses
        WHERE id = %s
        """

        cursor.execute(query, (expense_id,))

        self.connection.commit()

        print("Expense deleted successfully!")

     else:
         print("Deletion cancelled.")

     cursor.close()

    #monthly summary
    #_____________________________________________________________________
    def monthly_summary(self):

        month_input = input("Enter month (MM-YYYY): ")

        try:
            datetime.strptime(month_input, "%m-%Y")
        except ValueError:
            print("Invalid format! Please use MM-YYYY.")
            return

        month, year = month_input.split("-")

        cursor = self.connection.cursor()

        # Total spending
        query = """
        SELECT SUM(amount)
        FROM expenses
        WHERE MONTH(expense_date) = %s
        AND YEAR(expense_date) = %s
        """

        cursor.execute(query, (int(month), int(year)))

        result = cursor.fetchone()

        total = result[0]

        if total is None:
            total = 0

        print("\nMONTHLY SUMMARY")
        print("-" * 50)
        print("Month:", month_input)
        print("Total Spending:", total)

        # Spending by category
        query = """
        SELECT category, SUM(amount)
        FROM expenses
        WHERE MONTH(expense_date) = %s
        AND YEAR(expense_date) = %s
        GROUP BY category
        """

        cursor.execute(query, (int(month), int(year)))

        category_expenses = cursor.fetchall()

        print("\nSpending by Category")
        print("-" * 50)

        if not category_expenses:
            print("No expenses found for this month.")
        else:
            for category, amount in category_expenses:
                print(category, ":", amount)

        # Highest expense
        query = """
        SELECT id, category, amount, description
        FROM expenses
        WHERE MONTH(expense_date) = %s
        AND YEAR(expense_date) = %s
        ORDER BY amount DESC
        LIMIT 1
        """

        cursor.execute(query, (int(month), int(year)))

        highest = cursor.fetchone()

        if highest:
            print("\nHighest Expense")
            print("-" * 50)
            print("ID:", highest[0])
            print("Category:", highest[1])
            print("Amount:", highest[2])
            print("Description:", highest[3])

        cursor.close()

#setting budget
#__________________________________________________________________________
    def set_budget(self):
            month_input = input("Enter month to set budget (MM-YYYY): ")
            try:
                datetime.strptime(month_input, "%m-%Y")
            except ValueError:
                print("Invalid format! Please use MM-YYYY.")
                return

            month, year = month_input.split("-")

            month = int(month)
            year = int(year)

            try:
                amount = float(input("Enter amount to set budget: "))

                if amount <= 0:
                    print("Budget amount must be greater than 0.")
                    return

            except ValueError:
                print("Please enter a valid amount.")
                return

            cursor = self.connection.cursor()

            cursor.execute(
                """
                SELECT budget_amount
                FROM budgets
                WHERE month = %s AND year = %s
                """,
                (month, year)
            )

            existing_budget = cursor.fetchone()

            # If budget exists update it
            if existing_budget:

                cursor.execute(
                    """
                    UPDATE budgets
                    SET budget_amount = %s
                    WHERE month = %s AND year = %s
                    """,
                    (amount, month, year)
                )

                print("Budget updated successfully!")
            else:

                cursor.execute(
                    """
                    INSERT INTO budgets
                    (month, year, budget_amount)
                    VALUES (%s, %s, %s)
                    """,
                    (month, year, amount)
                )

                print("Budget added successfully!")

            self.connection.commit()

            cursor.execute(
                """
                SELECT SUM(amount)
                FROM expenses
                WHERE MONTH(expense_date) = %s
                AND YEAR(expense_date) = %s
                """,
                (month, year)
            )

            result = cursor.fetchone()

            if result[0] is None:
                spent = 0
            else:
                spent = float(result[0])

            remaining = amount - spent

            print("\nBUDGET DETAILS")
            print("-" * 50)
            print("Month          :", f"{month:02d}-{year}")
            print("Budget Amount  :", f"{amount:.2f}")
            print("Amount Spent   :", f"{spent:.2f}")
            print("Remaining      :", f"{remaining:.2f}")

            if remaining < 0:

                print("\n⚠ WARNING!")
                print(
                    "Budget exceeded by:",
                    f"{abs(remaining):.2f}"
                )

            elif remaining == 0:

                print("\n⚠ You have used your entire budget!")

            else:

                print("\n✓ You are within your budget.")

            cursor.close()

tracker = ExpenseTracker()


while True:

    print("\nPERSONAL EXPENSE TRACKER")
    print("1. Add Expense")
    print("2. View Expenses")
    print("3. Search Expense")
    print("4. Edit Expense")
    print("5. Monthly Summary")
    print("6. Set Budget")
    print("7. delete expense data")
    print("8. Exit")

    choice = input("Enter choice: ")

    if choice == "1":
        tracker.add_expense()

    elif choice == "2":
        tracker.view_expenses()

    elif choice == "3":
        tracker.search_expense()

    elif choice=="4":
        tracker.edit_expense()

    elif choice == "5":
        tracker.monthly_summary()

    elif choice == "6":
        tracker.set_budget()

    elif choice == "7":
        tracker.expense_deletion()

    elif choice == "8":
        print("Thank you for using Expense Tracker!")
        break
    else:
        print("Invalid choice!")

