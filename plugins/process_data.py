import sys
import argparse
import time
import os

print("Process Data Plugin Started.")
print(f"Arguments received by script: {sys.argv}")  # sys.argv[0] is the script name

parser = argparse.ArgumentParser(description="Processes some data.")
parser.add_argument("--input-file", required=True, help="Path to the input data file.")
parser.add_argument("--output-file", default="output.txt", help="Path to save the output.")
parser.add_argument("--iterations", type=int, default=1, help="Number of processing iterations.")

try:
    # argparse by default parses sys.argv[1:]
    # If your main app constructs the arg list like ['--input-file', 'mydata.txt', '--iterations', '3']
    # then you don't need to pass anything specific to parse_args()
    args = parser.parse_args()

    print(f"Processing input file: {args.input_file}")
    print(f"Output will be saved to: {args.output_file}")
    print(f"Number of iterations: {args.iterations}")

    # Create a dummy input file if it doesn't exist for testing
    if not os.path.exists(args.input_file):
        print(f"Note: Input file '{args.input_file}' not found. Creating a dummy one for testing.")
        with open(args.input_file, "w") as dummy_in:
            dummy_in.write("This is dummy input data.\nLine 2.\n")

    for i in range(args.iterations):
        print(f"Iteration {i + 1}/{args.iterations}...")
        # Simulate work
        time.sleep(0.5)

    # 尝试从标准输入读取一行
    try:
        print("\nAttempting to read a line from stdin (e.g., for a confirmation):")
        # In the current PluginManager setup, stdin is closed, so input() will raise EOFError or return ""
        user_confirmation = input("Type something and press Enter (will likely be EOF or error): ")
        if user_confirmation:  # This block will likely not execute if stdin is closed
            print(f"Stdin read: '{user_confirmation}'")
        else:
            print("Stdin was empty (EOF received, as expected if stdin is closed by parent).")
    except EOFError:
        print("EOFError received when trying to read from stdin (this is expected if parent closed stdin).")
    except Exception as e_input:
        # Depending on OS and Python version, other errors like "Bad file descriptor" might occur if stdin is closed.
        print(f"Error/Exception reading from stdin (possibly expected): {type(e_input).__name__}: {e_input}")

    with open(args.output_file, "w") as outfile:
        outfile.write(f"Processed {args.input_file} with {args.iterations} iterations.\n")
        outfile.write("This is a dummy output file from process_data.py plugin.\n")

    print(f"Successfully processed and saved to {args.output_file}")

except SystemExit as e:  # Argparse calls sys.exit on --help or error
    print(f"Argparse exited (e.g. due to --help or invalid arguments). Exit code: {e.code}")
    # sys.exit(e.code if e.code is not None else 1) # Propagate exit code if needed
except Exception as e:
    print(f"Error in process_data.py: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)  # Indicate failure

print("Process Data Plugin Finished.")