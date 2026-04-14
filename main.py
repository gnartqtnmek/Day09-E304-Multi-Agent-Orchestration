import os
import sys
from graph import run_graph

def main():
    """
    Giao diện chính để tương tác với hệ thống trợ lý CS + IT Helpdesk.
    Sử dụng kiến trúc Multi-Agent để truy vấn ChromaDB và xử lý logic.
    """
    print("=" * 60)
    print("🤖 HỆ THỐNG TRỢ LÝ NỘI BỘ (MULTI-AGENT RAG)")
    print("Hỗ trợ: CS Policy, IT Helpdesk, SLA & Access Control")
    print("=" * 60)
    print("Gõ 'exit' hoặc 'quit' để thoát.\n")

    while True:
        try:
            user_query = input("Câu hỏi của bạn: ").strip()
            
            if user_query.lower() in ["exit", "quit"]:
                print("Cảm ơn bạn đã sử dụng hệ thống. Tạm biệt!")
                break
            
            if not user_query:
                continue

            print("\n[Hệ thống] Đang phân tích và điều phối...")
            
            # Gọi Orchestrator (Supervisor) xử lý
            result = run_graph(user_query)

            print("\n" + "─" * 40)
            print(f"📝 TRẢ LỜI:\n{result['final_answer']}")
            print("─" * 40)
            print(f"🔍 Nguồn: {', '.join(result['sources']) if result['sources'] else 'Không tìm thấy nguồn'}")
            print(f"🤖 Workers hỗ trợ: {', '.join(result['workers_called'])}")
            print(f"✅ Độ tin cậy: {result['confidence']*100:.1f}% | ⏱️ Latency: {result['latency_ms']}ms")
            print("─" * 40 + "\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Có lỗi xảy ra: {str(e)}")

if __name__ == "__main__":
    main()