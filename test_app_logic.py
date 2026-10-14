import os
import pandas as pd
import database as db
import transmittance_analyzer as analyzer
import folder_watcher as watcher

def run_tests():
    print("=== Testing Database ===")
    db.init_db()
    
    sample_params = [
        {"step": 1, "current_A": 6.000, "speed_ums": 0.0, "start_time_s": 0.0, "stop_time_s": 160.0},
        {"step": 2, "current_A": 5.900, "speed_ums": 225.0, "start_time_s": 160.0, "stop_time_s": 230.0},
        {"step": 3, "current_A": 6.000, "speed_ums": 0.0, "start_time_s": 230.0, "stop_time_s": 430.0},
        {"step": 4, "current_A": 5.900, "speed_ums": 225.0, "start_time_s": 430.0, "stop_time_s": 530.0},
    ]

    print("=== Testing Transmittance Analyzer ===")
    csv_path = os.path.join(os.path.dirname(__file__), "sample_data", "sample_transmittance.csv")
    df_raw, err = analyzer.parse_transmittance_csv(csv_path)
    assert err is None, f"Error parsing CSV: {err}"
    print(f"Loaded CSV shape: {df_raw.shape}, columns: {list(df_raw.columns)}")

    df_norm, stats = analyzer.calculate_normalized_transmittance(
        df_raw,
        time_col="Time(s)",
        val_col="Transmittance(V)",
        baseline_mode="first"
    )
    print(f"Stats: Initial={stats['initial_val']}, Final={stats['final_pct']:.2f}%, Min={stats['min_pct']:.2f}%")
    assert abs(df_norm["transmittance_pct"].iloc[0] - 100.0) < 1e-4, "First value must be 100%!"

    fig = analyzer.create_transmittance_plot(
        df_norm,
        time_col="Time(s)",
        conditions=sample_params,
        title="Test Plot"
    )
    print(f"Plotly Figure created successfully with {len(fig.data)} traces and {len(fig.layout.shapes)} shapes.")

    print("=== Testing Database Save & Retrieve ===")
    test_db = os.path.join(os.path.dirname(__file__), "_test_logic_temp.db")
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass
    try:
        csv_cache = {
            "time": df_norm["Time(s)"].tolist(),
            "pct": df_norm["transmittance_pct"].tolist()
        }
        rec_id = db.save_record(
            sample_id="NF-20261007-SAMPLE",
            params=sample_params,
            photo_path=os.path.join(os.path.dirname(__file__), "sample_data", "sample_condition.jpg"),
            csv_path="sample_transmittance.csv",
            csv_data=csv_cache,
            initial_val=stats["initial_val"],
            final_pct=stats["final_pct"],
            min_pct=stats["min_pct"],
            notes="初期サンプル（添付画像条件のプリセットデータ）",
            db_path=test_db
        )
        print(f"Saved initial record with ID: {rec_id}")
        
        all_recs = db.get_all_records(db_path=test_db)
        print(f"Total records in test DB: {len(all_recs)}")
        assert len(all_recs) == 1

        # Test safe update without losing csv_data
        db.update_record(
            record_id=rec_id,
            sample_id="NF-20261007-SAMPLE-EDITED",
            params=sample_params,
            notes="Updated note only",
            csv_data=None, # should preserve existing csv_data
            db_path=test_db
        )
        updated_rec = db.get_record_by_id(rec_id, db_path=test_db)
        assert updated_rec["csv_data"] is not None, "csv_data must NOT be wiped when updating other fields!"
        assert updated_rec["sample_id"] == "NF-20261007-SAMPLE-EDITED"
        print("Safe update test passed! (csv_data preserved)")

        # Test JSON export and import
        exported_json = db.export_all_records_json(db_path=test_db)
        assert "NF-20261007-SAMPLE-EDITED" in exported_json
        print("JSON export test passed!")

        # Test import into a fresh DB
        fresh_test_db = os.path.join(os.path.dirname(__file__), "_test_import_temp.db")
        if os.path.exists(fresh_test_db):
            os.remove(fresh_test_db)
        try:
            import_res = db.import_records_from_json(exported_json, db_path=fresh_test_db)
            assert import_res["success"] is True
            assert import_res["imported_count"] == 1
            fresh_recs = db.get_all_records(include_csv_data=True, db_path=fresh_test_db)
            assert len(fresh_recs) == 1
            assert fresh_recs[0]["has_csv"] is True
            print("Smart merge & import test passed!")
        finally:
            if os.path.exists(fresh_test_db):
                try:
                    os.remove(fresh_test_db)
                except Exception:
                    pass

    finally:
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass

    print("=== Testing Folder Watcher ===")
    status = watcher.check_watch_dir_status()
    print(f"Watch dir status: exists={status['exists']}, count={status['image_count']}")

    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
