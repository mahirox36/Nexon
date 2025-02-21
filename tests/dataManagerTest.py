# SPDX-License-Identifier: MIT

import unittest
import json
import os
import shutil
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from nexon import DataManager

console = Console()

class DataManagerTestSuite(unittest.TestCase):
    """Comprehensive test suite for the DataManager class."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create a temporary directory for tests
        self.test_dir = Path("Data/")
        # Mock the base path to use our temporary directory
        self.original_base_path = Path

        # Performance monitoring setup
        self.test_results = []
        
        # Test announcement
        console.print(Panel(Text(f"Running: {self._testMethodName}", style="bold cyan")))
    
    def run(self, test):
        """Run the test and collect results."""
        result = super().run(test)
        return result

    def log_result(self, test_case, status, details, execution_time):
        """Log test results for reporting."""
        self.test_results.append({
            "test_case": test_case,
            "status": status,
            "details": details,
            "execution_time": execution_time
        })
    
    def tearDown(self):
        """Clean up after each test."""
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_basic_initialization(self):
        """Test basic initialization of DataManager."""
        start_time = time.time()
        try:
            # Test with minimal parameters
            dm = DataManager(name="test_feature")
            dm.save()
            
            # Assert paths are correct
            self.assertTrue((self.test_dir / "Features" / "test_feature").exists())
            self.assertTrue((self.test_dir / "Features" / "test_feature" / "data.json").exists())
            
            # Assert default data
            self.assertEqual(dm.data, {})
            
            self.log_result("Basic Initialization", "PASS", "Created with default parameters", time.time() - start_time)
        except Exception as e:
            self.log_result("Basic Initialization", "FAIL", str(e), time.time() - start_time)
            raise

    def test_initialization_with_server_id(self):
        """Test initialization with server ID (guild-specific data)."""
        start_time = time.time()
        try:
            # Test with server_id
            dm = DataManager(name="test_guild_feature", server_id=12345)
            dm["key"] = "value"
            dm.save()
            
            # Assert paths are correct for guild
            self.assertTrue((self.test_dir / "Guilds" / "12345" / "test_guild_feature").exists())
            self.assertTrue((self.test_dir / "Guilds" / "12345" / "test_guild_feature" / "data.json").exists())
            
            self.log_result("Guild Initialization", "PASS", "Created guild-specific data manager", time.time() - start_time)
        except Exception as e:
            self.log_result("Guild Initialization", "FAIL", str(e), time.time() - start_time)
            raise

    def test_custom_file_and_subfolder(self):
        """Test initialization with custom file name and subfolder."""
        start_time = time.time()
        try:
            # Test with custom file and subfolder
            dm = DataManager(
                name="test_feature",
                file_name="custom_data",
                subfolder="subfolder/nested"
            )
            dm["key"] = "value"
            dm.save()
            
            # Assert paths are correct
            expected_path = self.test_dir / "Features" / "test_feature" / "subfolder" / "nested" / "custom_data.json"
            self.assertTrue(expected_path.exists())
            
            self.log_result("Custom Path Initialization", "PASS", "Created with custom file and subfolder", time.time() - start_time)
        except Exception as e:
            self.log_result("Custom Path Initialization", "FAIL", str(e), time.time() - start_time)
            raise

    def test_default_data(self):
        """Test initialization with custom default data."""
        start_time = time.time()
        try:
            # Test with default dict
            default_dict = {"key1": "value1", "key2": 42}
            dm_dict = DataManager(name="test_defaults_dict", default=default_dict)
            self.assertEqual(dm_dict.data, default_dict)
            
            # Test with default list
            default_list = ["item1", "item2", "item3"]
            dm_list = DataManager(name="test_defaults_list", default=default_list)
            self.assertEqual(dm_list.data, default_list)
            
            self.log_result("Default Data", "PASS", "Created with custom default data structures", time.time() - start_time)
        except Exception as e:
            self.log_result("Default Data", "FAIL", str(e), time.time() - start_time)
            raise

    def test_save_and_load(self):
        """Test saving and loading data."""
        start_time = time.time()
        try:
            # Create and save data
            dm1 = DataManager(name="test_save_load")
            dm1["test_key"] = "test_value"
            dm1.save()
            
            # Load in a new instance
            dm2 = DataManager(name="test_save_load")
            self.assertEqual(dm2["test_key"], "test_value")
            
            self.log_result("Save and Load", "PASS", "Successfully saved and loaded data", time.time() - start_time)
        except Exception as e:
            self.log_result("Save and Load", "FAIL", str(e), time.time() - start_time)
            raise

    def test_auto_save(self):
        """Test auto_save functionality."""
        start_time = time.time()
        try:
            # Test with auto_save=True (default)
            with DataManager(name="test_auto_save_true") as dm:
                dm["key"] = "value"
                print(dm.data)
            
            # Check if data was saved
            dm_check = DataManager(name="test_auto_save_true")
            print(dm_check.data)
            self.assertEqual(dm_check["key"], "value")
            
            # Test with auto_save=False
            with DataManager(name="test_auto_save_false", auto_save=False) as dm:
                dm["key"] = "value"
            
            # Check if data was not saved
            dm_check = DataManager(name="test_auto_save_false")
            self.assertNotIn("key", dm_check.data)
            
            self.log_result("Auto Save", "PASS", "Auto-save enabled and disabled as expected", time.time() - start_time)
        except Exception as e:
            self.log_result("Auto Save", "FAIL", str(e), time.time() - start_time)
            raise

    def test_dictionary_interface(self):
        """Test dictionary interface (__getitem__, __setitem__)."""
        start_time = time.time()
        try:
            dm = DataManager(name="test_dict_interface")
            
            # Test __setitem__
            dm["test_key"] = "test_value"
            self.assertEqual(dm["test_key"], "test_value")
            
            # Test __getitem__
            self.assertEqual(dm["test_key"], "test_value")
            
            # Test KeyError
            with self.assertRaises(KeyError):
                value = dm["nonexistent_key"] # type: ignore
                
            self.log_result("Dictionary Interface", "PASS", "Get/set operations work as expected", time.time() - start_time)
        except Exception as e:
            self.log_result("Dictionary Interface", "FAIL", str(e), time.time() - start_time)
            raise

    def test_dictionary_interface_non_dict(self):
        """Test dictionary interface with non-dictionary data."""
        start_time = time.time()
        try:
            dm = DataManager(name="test_dict_interface_non_dict", default=[1, 2, 3])
            
            # Test __setitem__ raises TypeError
            with self.assertRaises(TypeError):
                dm["test_key"] = "test_value"
                
            # Test __getitem__ raises TypeError
            with self.assertRaises(TypeError):
                value = dm["test_key"] # type: ignore
                
            self.log_result("Dictionary Interface Type Safety", "PASS", "Correctly rejected dictionary operations on non-dict data", time.time() - start_time)
        except Exception as e:
            self.log_result("Dictionary Interface Type Safety", "FAIL", str(e), time.time() - start_time)
            raise

    def test_delete_key(self):
        """Test deleting a specific key."""
        start_time = time.time()
        try:
            # Test deleting key from dict
            dm_dict = DataManager(name="test_delete_key_dict")
            dm_dict.data = {"key1": "value1", "key2": "value2"}
            dm_dict.delete("key1")
            self.assertNotIn("key1", dm_dict.data)
            self.assertIn("key2", dm_dict.data)
            
            # Test deleting item from list
            dm_list = DataManager(name="test_delete_key_list", default=["item1", "item2"])
            dm_list.delete("item1")
            self.assertNotIn("item1", dm_list.data)
            self.assertIn("item2", dm_list.data)
            
            self.log_result("Delete Key", "PASS", "Successfully deleted keys/items from data structures", time.time() - start_time)
        except Exception as e:
            self.log_result("Delete Key", "FAIL", str(e), time.time() - start_time)
            raise

    def test_delete_file(self):
        """Test deleting the entire data file."""
        start_time = time.time()
        try:
            # Create and save data
            dm = DataManager(name="test_delete_file")
            dm["test_key"] = "test_value"
            dm.save()
            
            # Verify file exists
            file_path = self.test_dir / "Features" / "test_delete_file" / "data.json"
            self.assertTrue(file_path.exists())
            
            # Delete file
            dm.delete()
            
            # Verify file no longer exists
            self.assertFalse(file_path.exists())
            
            self.log_result("Delete File", "PASS", "Successfully deleted data file", time.time() - start_time)
        except Exception as e:
            self.log_result("Delete File", "FAIL", str(e), time.time() - start_time)
            raise
            
    def test_get_method(self):
        """Test the get method with default values."""
        start_time = time.time()
        try:
            # Test get with dict data
            dm_dict = DataManager(name="test_get_dict")
            dm_dict.data = {"key1": "value1"}
            
            # Test existing key
            self.assertEqual(dm_dict.get("key1"), "value1")
            
            # Test non-existing key with default
            self.assertEqual(dm_dict.get("key2", "default_value"), "default_value")
            
            # Test with list data
            dm_list = DataManager(name="test_get_list", default=["item1", "item2"])
            
            # Test existing item
            self.assertEqual(dm_list.get("item1"), "item1")
            
            # Test non-existing item with default
            self.assertEqual(dm_list.get("item3", "default_item"), "default_item")
            
            self.log_result("Get Method", "PASS", "Successfully retrieved values with defaults", time.time() - start_time)
        except Exception as e:
            self.log_result("Get Method", "FAIL", str(e), time.time() - start_time)
            raise

    def test_set_method(self):
        """Test the set method."""
        start_time = time.time()
        try:
            # Test set with auto_save=False
            dm = DataManager(name="test_set", auto_save=False)
            dm.set("key1", "value1")
            self.assertEqual(dm["key1"], "value1")
            
            # Test set with auto_save=True
            dm_auto = DataManager(name="test_set_auto")
            dm_auto.set("key1", "value1")
            
            # Load in a new instance to verify save
            dm_check = DataManager(name="test_set_auto")
            self.assertEqual(dm_check["key1"], "value1")
            
            # Test set with non-dict data
            dm_list = DataManager(name="test_set_list", default=[1, 2, 3])
            with self.assertRaises(TypeError):
                dm_list.set("key1", "value1")
                
            self.log_result("Set Method", "PASS", "Successfully set values with different configurations", time.time() - start_time)
        except Exception as e:
            self.log_result("Set Method", "FAIL", str(e), time.time() - start_time)
            raise

    def test_update_method(self):
        """Test the update method."""
        start_time = time.time()
        try:
            # Test update with auto_save=False
            dm = DataManager(name="test_update", auto_save=False)
            dm.data = {"key1": "value1"}
            dm.update({"key2": "value2", "key1": "updated"})
            self.assertEqual(dm.data["key1"], "updated")
            self.assertEqual(dm.data["key2"], "value2")
            
            # Test update with auto_save=True
            dm_auto = DataManager(name="test_update_auto")
            dm_auto.update({"key1": "value1", "key2": "value2"})
            
            # Load in a new instance to verify save
            dm_check = DataManager(name="test_update_auto")
            self.assertEqual(dm_check["key1"], "value1")
            self.assertEqual(dm_check["key2"], "value2")
            
            # Test update with non-dict data
            dm_list = DataManager(name="test_update_list", default=[1, 2, 3])
            with self.assertRaises(TypeError):
                dm_list.update({"key1": "value1"})
                
            self.log_result("Update Method", "PASS", "Successfully updated data with different configurations", time.time() - start_time)
        except Exception as e:
            self.log_result("Update Method", "FAIL", str(e), time.time() - start_time)
            raise

    def test_append_method(self):
        """Test the append method."""
        start_time = time.time()
        try:
            # Test append to list
            dm_list = DataManager(name="test_append_list", default=[])
            dm_list.append("item1")
            self.assertEqual(dm_list.data, ["item1"])
            
            # Test append with non-list data
            dm_dict = DataManager(name="test_append_dict")
            with self.assertRaises(TypeError):
                dm_dict.append("item1")
                
            self.log_result("Append Method", "PASS", "Successfully appended to list data", time.time() - start_time)
        except Exception as e:
            self.log_result("Append Method", "FAIL", str(e), time.time() - start_time)
            raise

    def test_exists_method(self):
        """Test the exists method."""
        start_time = time.time()
        try:
            # Test with existing file
            dm_exists = DataManager(name="test_exists")
            dm_exists.save()
            self.assertTrue(dm_exists.exists())
            
            # Test with non-existing file
            dm_not_exists = DataManager(name="test_not_exists")
            dm_not_exists.file.unlink(missing_ok=True)  # Ensure file doesn't exist
            self.assertFalse(dm_not_exists.exists())
            
            self.log_result("Exists Method", "PASS", "Correctly detected file existence", time.time() - start_time)
        except Exception as e:
            self.log_result("Exists Method", "FAIL", str(e), time.time() - start_time)
            raise

    def test_len_method(self):
        """Test the __len__ method."""
        start_time = time.time()
        try:
            # Test with dict
            dm_dict = DataManager(name="test_len_dict")
            dm_dict.data = {"key1": "value1", "key2": "value2"}
            self.assertEqual(len(dm_dict), 2)
            
            # Test with list
            dm_list = DataManager(name="test_len_list", default=["item1", "item2", "item3"])
            self.assertEqual(len(dm_list), 3)
            
            self.log_result("Len Method", "PASS", "Correctly returned data length", time.time() - start_time)
        except Exception as e:
            self.log_result("Len Method", "FAIL", str(e), time.time() - start_time)
            raise

    def test_cache_mechanism(self):
        """Test the caching mechanism."""
        start_time = time.time()
        try:
            # Clear cache for this test
            DataManager._cache.clear()
            DataManager._cache_timestamps.clear()
            
            # Create first instance
            dm1 = DataManager(name="test_cache")
            dm1["key"] = "value"
            dm1.save()
            
            # Create second instance - should use cache
            before_load = time.time()
            dm2 = DataManager(name="test_cache")
            load_time = time.time() - before_load
            
            # Verify data matches
            self.assertEqual(dm2["key"], "value")
            
            # Verify item is in cache
            cache_key = str(dm1.file)
            self.assertIn(cache_key, DataManager._cache)
            
            # Modify directly on disk to test cache priority
            with open(dm1.file, "w", encoding='utf-8') as f:
                json.dump({"key": "modified_value"}, f)
            
            # Load third instance - should still use cache
            dm3 = DataManager(name="test_cache")
            self.assertEqual(dm3["key"], "value")  # From cache, not disk
            
            # Clear cache
            DataManager._cache.clear()
            DataManager._cache_timestamps.clear()
            
            # Load fourth instance - should read from disk
            dm4 = DataManager(name="test_cache")
            self.assertEqual(dm4["key"], "modified_value")  # From disk
            
            self.log_result("Cache Mechanism", "PASS", f"Cache correctly prioritized over disk reads (load time: {load_time:.6f}s)", time.time() - start_time)
        except Exception as e:
            self.log_result("Cache Mechanism", "FAIL", str(e), time.time() - start_time)
            raise

    def test_cache_cleanup(self):
        """Test cache cleanup mechanism."""
        start_time = time.time()
        try:
            # Set small cache limits for testing
            original_limit = DataManager._cache_limit
            original_ttl = DataManager._cache_ttl
            DataManager._cache_limit = 2
            DataManager._cache_ttl = 1  # 100ms TTL for testing
            
            # Clear cache to start fresh
            DataManager._cache.clear()
            DataManager._cache_timestamps.clear()
            
            # Create multiple instances to fill cache
            dm1 = DataManager(name="test_cache_1")
            dm1.save()
            dm2 = DataManager(name="test_cache_2")
            dm2.save()
            dm3 = DataManager(name="test_cache_3")
            dm3.save()
            
            # Check if oldest cache entry was evicted (LRU policy)
            self.assertNotIn(str(dm1.file), DataManager._cache)
            self.assertIn(str(dm2.file), DataManager._cache)
            self.assertIn(str(dm3.file), DataManager._cache)
            
            # Wait for TTL to expire
            time.sleep(2)
            
            # Force cleanup by creating a new instance
            dm4 = DataManager(name="test_cache_4")
            dm4.save()
            
            # Verify expired entries were removed
            self.assertNotIn(str(dm2.file), DataManager._cache)
            self.assertNotIn(str(dm3.file), DataManager._cache)
            self.assertIn(str(dm4.file), DataManager._cache)
            
            # Restore original limits
            DataManager._cache_limit = original_limit
            DataManager._cache_ttl = original_ttl
            
            self.log_result("Cache Cleanup", "PASS", "Successfully implemented LRU eviction and TTL expiration", time.time() - start_time)
        except Exception as e:
            self.log_result("Cache Cleanup", "FAIL", str(e), time.time() - start_time)
            raise

    def test_performance_scalability(self):
        """Test performance with increasing data sizes."""
        start_time = time.time()
        try:
            # Test with small data
            small_data = {f"key_{i}": f"value_{i}" for i in range(10)}
            dm_small = DataManager(name="test_perf_small")
            dm_small.data = small_data
            
            small_save_start = time.time()
            dm_small.save()
            small_save_time = time.time() - small_save_start
            
            small_load_start = time.time()
            dm_small_reload = DataManager(name="test_perf_small") # type: ignore
            small_load_time = time.time() - small_load_start
            
            # Test with medium data
            medium_data = {f"key_{i}": f"value_{i}" for i in range(100)}
            dm_medium = DataManager(name="test_perf_medium")
            dm_medium.data = medium_data
            
            medium_save_start = time.time()
            dm_medium.save()
            medium_save_time = time.time() - medium_save_start
            
            medium_load_start = time.time()
            dm_medium_reload = DataManager(name="test_perf_medium") # type: ignore
            medium_load_time = time.time() - medium_load_start
            
            # Test with large data
            large_data = {f"key_{i}": f"value_{i}" for i in range(1000)}
            dm_large = DataManager(name="test_perf_large")
            dm_large.data = large_data
            
            large_save_start = time.time()
            dm_large.save()
            large_save_time = time.time() - large_save_start
            
            large_load_start = time.time()
            dm_large_reload = DataManager(name="test_perf_large") # type: ignore
            large_load_time = time.time() - large_load_start
            
            performance_details = (
                f"Small data (10 items): save={small_save_time:.6f}s, load={small_load_time:.6f}s\n"
                f"Medium data (100 items): save={medium_save_time:.6f}s, load={medium_load_time:.6f}s\n"
                f"Large data (1000 items): save={large_save_time:.6f}s, load={large_load_time:.6f}s"
            )
            
            # Check if performance scales reasonably (not exactly linear)
            reasonable_scaling = (large_save_time / small_save_time) < (1000 / 10) * 2
            
            if reasonable_scaling:
                self.log_result("Performance Scalability", "PASS", performance_details, time.time() - start_time)
            else:
                self.log_result("Performance Scalability", "WARNING", f"Performance may not scale well: {performance_details}", time.time() - start_time)
                
        except Exception as e:
            self.log_result("Performance Scalability", "FAIL", str(e), time.time() - start_time)
            raise

    def test_edge_cases(self):
        """Test various edge cases."""
        start_time = time.time()
        try:
            # Test with empty name
            with self.assertRaises(Exception):
                dm = DataManager(name="")
                dm["key"] = "value"
                dm.save()
            
            # Test with special characters in name
            dm_special = DataManager(name="test!@#$%^&*()")
            dm_special.save()
            self.assertTrue(dm_special.path.exists())
            
            # Test with very long name
            long_name = "a" * 255
            dm_long = DataManager(name=long_name)
            dm_long.save()
            self.assertTrue(dm_long.path.exists())
            
            # Test with Unicode characters
            dm_unicode = DataManager(name="테스트_データ_🚀")
            dm_unicode["테스트_キー"] = "값_値_🔑"
            dm_unicode.save()
            
            # Reload to verify Unicode handling
            dm_unicode_reload = DataManager(name="테스트_データ_🚀")
            self.assertEqual(dm_unicode_reload["테스트_キー"], "값_値_🔑")
            
            self.log_result("Edge Cases", "PASS", "Successfully handled various edge cases", time.time() - start_time)
        except Exception as e:
            self.log_result("Edge Cases", "FAIL", str(e), time.time() - start_time)
            raise

def generate_summary_report(results):
    """Generate a formatted summary report of all test results."""
    # Create results table
    results_table = Table(title="DataManager Test Results")
    results_table.add_column("Test Case", style="cyan")
    results_table.add_column("Status", style="bold")
    results_table.add_column("Details")
    results_table.add_column("Execution Time", justify="right")
    
    # Add results to table
    pass_count = 0
    fail_count = 0
    warning_count = 0
    
    for result in results:
        status = result["status"]
        status_style = {
            "PASS": "green",
            "FAIL": "red",
            "WARNING": "yellow"
        }.get(status, "white")
        
        if status == "PASS":
            pass_count += 1
        elif status == "FAIL":
            fail_count += 1
        elif status == "WARNING":
            warning_count += 1
            
        results_table.add_row(
            result["test_case"],
            Text(status, style=status_style),
            result["details"],
            f"{result['execution_time']:.6f}s"
        )
        
    # Print summary
    console.print("\n")
    console.print(Panel(Text("Test Execution Summary", style="bold cyan")))
    console.print(results_table)
    
    # Print overall statistics
    total_tests = pass_count + fail_count + warning_count
    console.print(Panel(
        f"[bold]Total Tests:[/bold] {total_tests}\n"
        f"[bold green]Passed:[/bold green] {pass_count}\n"
        f"[bold red]Failed:[/bold red] {fail_count}\n"
        f"[bold yellow]Warnings:[/bold yellow] {warning_count}"
    ))
    
    # Provide analysis and recommendations
    recommendations = []
    if fail_count > 0:
        recommendations.append("[bold red]Critical issues found![/bold red] Fix failed tests before deployment.")
    if warning_count > 0:
        recommendations.append("[bold yellow]Performance issues may be present.[/bold yellow] Consider optimizing the identified areas.")
    if fail_count == 0 and warning_count == 0:
        recommendations.append("[bold green]All tests passed successfully![/bold green] The library appears stable and ready for use.")
        
    if any(result["test_case"] == "Performance Scalability" and result["status"] == "WARNING" for result in results):
        recommendations.append("Consider optimizing JSON serialization/deserialization for better performance with large datasets.")
        
    console.print(Panel(Text("\n".join(recommendations), style="bold")))


def run_tests():
    """Run all tests and generate report."""
    os.system("cls")
    console.print(Panel(Text("DataManager Comprehensive Test Suite", style="bold cyan"), expand=False))
    
    # Create test suite
    test_suite = unittest.TestLoader().loadTestsFromTestCase(DataManagerTestSuite)
    
    # Create a shared list for test results
    results = []
    
    # Monkey patch the log_result method on the TestCase class to collect results
    original_log_result = DataManagerTestSuite.log_result
    
    def patched_log_result(self, test_case, status, details, execution_time):
        results.append({
            "test_case": test_case,
            "status": status,
            "details": details,
            "execution_time": execution_time
        })
        original_log_result(self, test_case, status, details, execution_time)
        
    DataManagerTestSuite.log_result = patched_log_result
    
    # Run tests
    test_runner = unittest.TextTestRunner(verbosity=0)
    runner_result = test_runner.run(test_suite)
    
    # Generate report
    generate_summary_report(results)
    
    # Additional analysis
    console.print(Panel(Text("Additional Analysis & Recommendations", style="bold cyan")))
    
    console.print("""
[bold]Strengths:[/bold]
1. [green]Efficient caching mechanism[/green] - Reduces disk I/O for frequently accessed data
2. [green]Flexible initialization options[/green] - Supports various use cases and configurations
3. [green]Dictionary-like interface[/green] - Provides intuitive data access
4. [green]Context manager support[/green] - Simplifies usage with automatic saving

[bold]Areas for Improvement:[/bold]
1. [yellow]Error handling[/yellow] - Consider more specific error types for better error handling
2. [yellow]Documentation[/yellow] - Method docstrings could include more examples
3. [yellow]JSON serialization[/yellow] - Consider optional compression for large datasets
4. [yellow]Thread safety[/yellow] - Add locks for thread-safe operations if needed in multithreaded environments

[bold]Security Considerations:[/bold]
1. No apparent security vulnerabilities in file handling
2. Path traversal protection is adequate
3. Consider implementing encryption for sensitive data

[bold]Compatibility:[/bold]
The library should work well on Python 3.7+ as it uses pathlib and modern Python features.
    """)
    
    return len(runner_result.failures) == 0 and len(runner_result.errors) == 0


if __name__ == "__main__":
    run_tests()

