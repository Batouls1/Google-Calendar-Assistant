from app.agent.agent import create_calendar_agent


def main():
    print("Google Calendar Assistant")
    print("Type 'quit' to exit.\n")

    agent = create_calendar_agent()
    config = {"configurable": {"thread_id": "main-session"}}

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )
        output = result["messages"][-1].content
        print(f"\nAssistant: {output}\n")


if __name__ == "__main__":
    main()    