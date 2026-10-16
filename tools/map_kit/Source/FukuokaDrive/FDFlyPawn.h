#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "FDFlyPawn.generated.h"

class UCameraComponent;
class UInputAction;
class UInputMappingContext;
class USceneComponent;
struct FInputActionValue;

/**
 * 自由に飛び回るカメラ (B キー)。クロスカブに乗っていても歩いていても、B でその場のカメラの位置から飛び立ち、
 * もう一度 B で元のバイクか人に戻る (バイクと人はその場に止まったまま待つ)。
 *
 * - W/A/S/D で見ている向きへ進む、E / Space で上がる、Q / Ctrl で下がる、マウスで見回す
 * - Shift を押している間は速く、マウスのホイールで速さを変える (画面左上に出る)
 * - 地面や海面の下には潜らない (地面から GroundClearanceCm 上で止まる)。木や建物は通り抜ける
 * - 時刻 (T/G、1-4) と季節 (Y) はそのまま使える
 */
UCLASS()
class FUKUOKADRIVE_API AFDFlyPawn : public APawn
{
	GENERATED_BODY()

public:
	AFDFlyPawn();

	/** From を操作しているプレイヤーを、From のカメラの位置から飛ばす。戻る先は From */
	static AFDFlyPawn* StartFrom(APawn* From);

	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PawnClientRestart() override;
	virtual void UnPossessed() override;

	/** 飛び立った元のバイクか人に戻る (B キー) */
	UFUNCTION(BlueprintCallable, Category = "Fly")
	void ReturnToGround();

	/** 地図で選んだ XY (UE 座標 cm) の上空へ移る。地面からの高さは今のまま (低ければ MinTravelHeightCm) */
	void FlyTo(const FVector2D& XY);

	/** 地図で移ったときの、地面からの最低の高さ (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	float MinTravelHeightCm = 3000.f;

	/** ふつうの速さ (cm/s)。2500 で 90 km/h */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	float SpeedCms = 2500.f;

	/** Shift を押している間の速さの倍率 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	float BoostScale = 5.f;

	/** ホイールで変えられる速さの倍率の範囲 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	FVector2D SpeedScaleRange = FVector2D(0.1f, 20.f);

	/** 速さが目標に追いつく早さ (1/s)。大きいほどきびきび止まる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	float Responsiveness = 4.f;

	/** 地面 (と海面) からこれより下へは下がらない (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	float GroundClearanceCm = 150.f;

	/** これより上へは上がらない (cm、海面から) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	float MaxAltitudeCm = 500000.f;

	/** マウスを動かした量 1 あたりに回す角度 (度)。歩くときと同じ */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	float MouseLookScale = 2.5f;

	/** スティックを倒しきったときに回す速さ (度/秒) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	float StickLookRateDeg = 90.f;

	/** 画面左上に速さと操作を表示する */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Fly")
	bool bShowDebugText = true;

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> Root;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UCameraComponent> Camera;

private:
	void CreateInputAssets();
	void Look(const FVector2D& DeltaDeg);
	/** Location の真下の地面の高さ (無ければ海面 0)。景観物は当たり判定が無いので地形だけに当たる */
	float GroundZBelow(const FVector& Location) const;

	UPROPERTY(Transient)
	TObjectPtr<APawn> ReturnPawn;

	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> MappingContext;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> MoveAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> UpDownAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LookAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LookStickAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> BoostAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SpeedAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ReturnAction;

	FVector2D MoveInput = FVector2D::ZeroVector;
	float UpDownInput = 0.f;
	bool bBoost = false;
	float SpeedScale = 1.f;
	FVector Velocity = FVector::ZeroVector;

};
