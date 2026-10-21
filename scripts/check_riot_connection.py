
import os

from dotenv import load_dotenv

from ingestion.riot_client import RiotClient


def main():
    load_dotenv()

    client = RiotClient()

    account = client.get_account(
        game_name=os.environ["RIOT_GAME_NAME"],
        tag_line=os.environ["RIOT_TAG_LINE"]
    )

    match_ids = client.get_all_match_ids(
        puuid=account["puuid"],
        max_matches=5,
        page_size=5
    )

    print("Connexion Riot API : OK")
    print(f"Matchs récupérés : {len(match_ids)}")

    if not match_ids:
        return

    match = client.get_match(match_ids[0])
    timeline = client.get_timeline(match_ids[0])

    print("Match ID :", match["metadata"]["matchId"])
    print("Participants :", len(match["info"]["participants"]))
    print("Frames :", len(timeline["info"]["frames"]))


if __name__ == "__main__":
    main()
